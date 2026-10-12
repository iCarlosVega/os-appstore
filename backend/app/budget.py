from uuid import uuid4
from . import db, store, discord
from .config import config

def period_now():
    return store.now()[:7]

def usage():
    with db.transaction():
        return _usage(store.get_settings(), period_now())

def _usage(settings, period):
    ai = int(db.query("SELECT COALESCE(SUM(amount),0) AS amount FROM cost_entries WHERE period=$1", [period])[0]["amount"])
    hosting = max(settings.hostingMicros or 0, settings.hostingActualMicros if settings.hostingActualPeriod == period else 0)
    return {"period": period, "ai": ai, "hosting": hosting, "total": ai + hosting, "budget": settings.budgetMicros, "configured": settings.hostingMicros is not None and settings.jevMicrosPerMillion is not None}

def _pause(settings):
    settings.budgetPaused = settings.aiPaused = settings.discoveryPaused = settings.maintenancePaused = True
    settings.revision += 1
    store.write_settings(settings)

def _enforce(settings, total):
    if total >= settings.budgetMicros and not settings.budgetPaused:
        _pause(settings)
        return discord.queue(f"Monthly operating target reached. Discovery, maintenance, and paid AI are paused. Review and explicitly resume: {config.app_url}/admin")

def enforce():
    with db.transaction():
        settings = store.get_settings()
        notice = _enforce(settings, _usage(settings, period_now())["total"])
        stopped = settings.budgetPaused
    if notice:
        discord.deliver(notice)
    return stopped

def reserve(amount: int):
    if type(amount) is not int or amount < 1:
        return None
    with db.transaction():
        reservation, notice = _reserve(amount, store.get_settings())
    if notice:
        discord.deliver(notice)
    return reservation

def _reserve(amount, settings):
    # Caller holds db.transaction so a provider can snapshot its rate under the same lock.
    if settings.aiPaused or settings.budgetPaused or settings.hostingMicros is None or settings.jevMicrosPerMillion is None:
        return None, None
    created_at = store.now()
    period = created_at[:7]
    total = _usage(settings, period)["total"] + amount
    if total > settings.budgetMicros:
        _pause(settings)
        return None, discord.queue("Remaining monthly allowance cannot cover the next AI call. Paid work is paused. Review and resume in the admin dashboard.")
    reservation = str(uuid4())
    db.query("INSERT INTO cost_entries(id,period,provider,amount,settled,created_at) VALUES($1,$2,'TypeSafe Jev',$3,0,$4)", [reservation, period, amount, created_at])
    return reservation, _enforce(settings, total)

def settle(reservation: str, amount: int):
    if type(amount) is not int or amount < 0:
        return
    with db.transaction():
        db.query("UPDATE cost_entries SET amount=$1,settled=1 WHERE id=$2", [amount, reservation])
        settings = store.get_settings()
        notice = _enforce(settings, _usage(settings, period_now())["total"])
    if notice:
        discord.deliver(notice)

def money(micros):
    return f"${micros / 1000000:.2f}"
