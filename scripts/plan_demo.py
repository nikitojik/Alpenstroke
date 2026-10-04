from sqlalchemy import select

from app.db import SessionLocal
from app.models import Athlete
from app.services.planner import generate_plan
from scripts.seed import DEMO_PREFIX


def main() -> None:
    with SessionLocal() as db:
        athletes = db.scalars(
            select(Athlete)
            .where(Athlete.name.startswith(DEMO_PREFIX))
            .order_by(Athlete.id)
        ).all()
        if not athletes:
            print("No demo athletes. Run: python -m scripts.seed")
            return

        for athlete in athletes:
            plan = generate_plan(db, athlete).recommendation
            change = plan["change_vs_last_week_pct"]
            change_text = f"{change:+d}%" if change is not None else "n/a"
            print(
                f"\n=== {athlete.name}  (goal: {athlete.goal_event} on {athlete.goal_date})"
            )
            print(
                f"total: {plan['total_distance_m']} m, last week: {plan['last_week_m']} m, "
                f"change: {change_text}"
            )
            target = plan.get("volume_target_m")
            if target:
                model_status = "hit" if plan["model_within_target"] else "missed"
                scaled = (
                    f", scaled x{plan['volume_scaled_by']}"
                    if plan["volume_scaled_by"]
                    else ""
                )
                print(
                    f"target: {target['min']}-{target['max']} m ({target['reason']}); "
                    f"model planned {plan['model_total_m']} m -> {model_status}{scaled}"
                )
            print(f"summary: {plan['summary']}")
            for d in plan["days"]:
                print(
                    f"  {d['date']}  {d['session_type']:<10} {d['distance_m']:>5} m  "
                    f"{d['main_set'] or '-':<32} {d['focus'] or '-'}"
                )
            if plan.get("cautions"):
                print(f"cautions: {plan['cautions']}")
            if plan.get("grounding_warnings"):
                print(f"!! not in notes: {', '.join(plan['grounding_warnings'])}")
            for warning in plan.get("rule_warnings", []):
                print(f"!! rule: {warning}")


if __name__ == "__main__":
    main()
