"""Human-in-the-loop review queue — PRD 6 (F11).

item_type: dedup | affiliation | author. Deciding a dedup item as 'reject'
records the pair in rejected_merges (ordered) so it never auto-merges again;
'approve' applies the merge immediately via dedup.apply_manual_merge.
"""
from datetime import datetime, timezone

from app.models import RejectedMerge, ReviewItem


def create_review_item(session, item_type: str, payload: dict, score=None) -> ReviewItem:
    """Create a pending item; dedupe identical pending dedup pairs."""
    if item_type == "dedup" and payload.get("record_a_id"):
        pair = tuple(sorted([payload["record_a_id"], payload["record_b_id"]]))
        existing = (
            session.query(ReviewItem)
            .filter_by(item_type="dedup", status="pending")
            .all()
        )
        for item in existing:
            p = item.payload or {}
            if tuple(sorted([p.get("record_a_id"), p.get("record_b_id")])) == pair:
                return item
    item = ReviewItem(item_type=item_type, payload=payload, score=score, status="pending")
    session.add(item)
    session.flush()
    return item


def list_pending_review_items(session, item_type: str | None = None) -> list:
    q = session.query(ReviewItem).filter_by(status="pending").order_by(ReviewItem.id)
    if item_type:
        q = q.filter_by(item_type=item_type)
    return q.all()


def decide_review_item(session, item_id: int, decision: str) -> dict:
    """decision: 'approve' | 'reject'. Returns what happened."""
    from app.services.dedup import apply_manual_merge  # local import: dedup imports review

    item = session.get(ReviewItem, item_id)
    if not item:
        return {"ok": False, "error": "not_found"}
    if item.status != "pending":
        return {"ok": False, "error": f"already_{item.status}"}
    if decision not in ("approve", "reject"):
        return {"ok": False, "error": "bad_decision"}

    item.status = "approved" if decision == "approve" else "rejected"
    item.decided_at = datetime.now(timezone.utc)
    result = {"ok": True, "decision": decision, "item_id": item_id}

    if item.item_type == "dedup":
        payload = item.payload or {}
        a_id, b_id = payload.get("record_a_id"), payload.get("record_b_id")
        if decision == "reject" and a_id and b_id:
            a, b = (a_id, b_id) if a_id <= b_id else (b_id, a_id)
            if not session.get(RejectedMerge, (a, b)):
                session.add(RejectedMerge(raw_record_a=a, raw_record_b=b))
            result["rejected_pair"] = [a, b]
        elif decision == "approve" and a_id and b_id:
            result["merge"] = apply_manual_merge(session, a_id, b_id)

    session.flush()
    return result
