from uuid import uuid4
from . import db, store, discord
from .config import config

def period_now():
    return store.now()[:7]

def usage():
    settings = store.get_settings()
    period = period_now()
    ai = int(db.query("SELECT COALESCE(SUM(amount),0) AS amount FROM cost_entries WHERE period=$1", [period])[0]["amount"])
    hosting = max(settings.hostingMicros or 0, settings.hostingActualMicros if settings.hostingActualPeriod == period else 0)
    return {"period": period, "ai": ai, "hosting": hosting, "total": ai + hosting, "budget": settings.budgetMicros, "configured": settings.hostingMicros is not None and settings.jevMicrosPerMillion is not None}

def _pause(settings):
    settings.budgetPaused = settings.aiPaused = settings.discoveryPaused = settings.maintenancePaused = True
    settings.revision += 1
    store.write_settings(settings)

def enforce():
    notice = None
    with db.transaction():
        settings = store.get_settings()
        if usage()["total"] >= settings.budgetMicros and not settings.budgetPaused:
            _pause(settings)
            notice = discord.queue(f"Monthly operating target reached. Discovery, maintenance, and paid AI are paused. Review and explicitly resume: {config.app_url}/admin")
        stopped = settings.budgetPaused
    if notice:
        discord.deliver(notice)
    return stopped

def reserve(amount: int):
    notice = None
    reservation = None
    with db.transaction():
        settings = store.get_settings()
        if settings.aiPaused or settings.budgetPaused or settings.hostingMicros is None or settings.jevMicrosPerMillion is None or amount < 1:
            return None
        if usage()["total"] + amount > settings.budgetMicros:
            _pause(settings)
            notice = discord.queue("Remaining monthly allowance cannot cover the next AI call. Paid work is paused. Review and resume in the admin dashboard.")
        else:
            reservation = str(uuid4())
            db.query("INSERT INTO cost_entries(id,period,provider,amount,settled,created_at) VALUES($1,$2,'TypeSafe Jev',$3,0,$4)", [reservation, period_now(), amount, store.now()])
    if notice:
        discord.deliver(notice)
    return reservation

def settle(reservation: str, amount: int):
    if amount < 0:
        return
    db.query("UPDATE cost_entries SET amount=$1,settled=1 WHERE id=$2", [amount, reservation])
    enforce()

def money(micros):
    return f"${micros / 1000000:.2f}"
