"""Idempotent local drawer and driver accounting for every order state change."""

from __future__ import annotations

from typing import Any


def _row_value(row: Any, index: int) -> Any:
    return row[index]


def reconcile_order_finance(conn, order_id: int, *, fallback_shift_id: int | None = None) -> bool:
    """Move only the delta between recorded and desired financial effects.

    The four marker columns live on the order, so repeating this function after
    a crash or a delayed website event is safe and does not duplicate money.
    """
    row = conn.execute(
        "SELECT payment_method, COALESCE(total, 0), COALESCE(delivery_fee, 0), "
        "channel, status, COALESCE(source, 'POS'), shift_id, driver_id, "
        "COALESCE(drawer_applied, 0), COALESCE(driver_applied, 0), "
        "financial_shift_id, financial_driver_id FROM orders WHERE id=?",
        (order_id,),
    ).fetchone()
    if not row:
        return False

    (payment_method, total, delivery_fee, channel, status, source, shift_id,
     driver_id, old_drawer, old_driver, old_shift_id, old_driver_id) = (
        _row_value(row, index) for index in range(12)
    )
    total = float(total or 0)
    delivery_fee = float(delivery_fee or 0)
    net_cash = max(0.0, total - delivery_fee)

    drawer_due = 0.0
    if payment_method == "CASH" and status != "CANCELLED":
        if source == "POS" and channel != "DELIVERY":
            drawer_due = net_cash
        elif status == "COMPLETED":
            drawer_due = net_cash

    target_shift_id = old_shift_id or shift_id or fallback_shift_id
    old_drawer = float(old_drawer or 0)
    drawer_delta = round(drawer_due - old_drawer, 2)
    if abs(drawer_delta) >= 0.005:
        if not target_shift_id:
            return False
        conn.execute(
            "UPDATE shifts SET expected_cash=MAX(0.0, COALESCE(expected_cash, 0)+?) WHERE id=?",
            (drawer_delta, target_shift_id),
        )

    driver_due = 0.0
    target_driver_id = None
    if driver_id and status == "DISPATCHED":
        target_driver_id = driver_id
        driver_due = net_cash if payment_method == "CASH" else -delivery_fee

    old_driver = float(old_driver or 0)
    if old_driver_id and (old_driver_id != target_driver_id or abs(old_driver - driver_due) >= 0.005):
        conn.execute(
            "UPDATE drivers SET unsettled_cash=COALESCE(unsettled_cash, 0)-? WHERE id=?",
            (old_driver, old_driver_id),
        )
        old_driver = 0.0
    if target_driver_id and abs(driver_due - old_driver) >= 0.005:
        conn.execute(
            "UPDATE drivers SET unsettled_cash=COALESCE(unsettled_cash, 0)+? WHERE id=?",
            (driver_due - old_driver, target_driver_id),
        )

    conn.execute(
        "UPDATE orders SET drawer_applied=?, driver_applied=?, "
        "financial_shift_id=?, financial_driver_id=? WHERE id=?",
        (drawer_due, driver_due, target_shift_id, target_driver_id, order_id),
    )
    return True


def cancel_and_reconcile(conn, order_id: int, *, fallback_shift_id: int | None = None) -> bool:
    """Reverse all effects before a local order is physically deleted."""
    found = conn.execute(
        "SELECT payment_method, COALESCE(total, 0), COALESCE(delivery_fee, 0), "
        "channel, COALESCE(source, 'POS'), status, COALESCE(drawer_applied, 0), "
        "shift_id FROM orders WHERE id=?",
        (order_id,),
    ).fetchone()
    if not found:
        return False
    # Orders made by older builds already entered pickup cash at checkout but
    # have no marker. Adopt that existing effect before reversing it.
    if (
        found[0] == "CASH" and found[3] != "DELIVERY" and found[4] == "POS"
        and found[5] != "CANCELLED" and abs(float(found[6] or 0)) < 0.005
    ):
        conn.execute(
            "UPDATE orders SET drawer_applied=?, financial_shift_id=? WHERE id=?",
            (
                max(0.0, float(found[1] or 0) - float(found[2] or 0)),
                found[7] or fallback_shift_id,
                order_id,
            ),
        )
    conn.execute(
        "UPDATE orders SET status='CANCELLED', driver_id=NULL WHERE id=?",
        (order_id,),
    )
    return reconcile_order_finance(conn, order_id, fallback_shift_id=fallback_shift_id)
