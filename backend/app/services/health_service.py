"""
AlmaDiet — Health Service
Handles health record creation, retrieval, and clinical analysis.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_record import HealthRecord
from app.models.user import User
from app.schemas.health import HealthRecordCreate, HealthAnalysis


async def create_health_record(
    db: AsyncSession, user_id: uuid.UUID, data: HealthRecordCreate
) -> HealthRecord:
    """Create a monthly health record with auto-computed BMI."""
    # Fetch user for height-based BMI calculation
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    bmi = data.bmi
    if bmi is None and user and user.height_cm:
        height_m = user.height_cm / 100.0
        bmi = round(data.current_weight_kg / (height_m ** 2), 1)

    record = HealthRecord(
        user_id=user_id,
        trimester=data.trimester,
        week_number=data.week_number,
        current_weight_kg=data.current_weight_kg,
        bmi=bmi,
        blood_pressure_sys=data.blood_pressure_sys,
        blood_pressure_dia=data.blood_pressure_dia,
        hemoglobin=data.hemoglobin,
        blood_sugar_fasting=data.blood_sugar_fasting,
        allergies=data.allergies or [],
        medical_conditions=data.medical_conditions or [],
        is_vegetarian=data.is_vegetarian,
        dietary_preference=data.dietary_preference,
        notes=data.notes,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_health_records(
    db: AsyncSession, user_id: uuid.UUID
) -> list[HealthRecord]:
    """Get all health records for a user, ordered by date descending."""
    result = await db.execute(
        select(HealthRecord)
        .where(HealthRecord.user_id == user_id)
        .order_by(HealthRecord.recorded_at.desc())
    )
    return list(result.scalars().all())


async def get_health_record_by_id(
    db: AsyncSession, record_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[HealthRecord]:
    """Get a specific health record."""
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id,
            HealthRecord.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


def analyze_health(record: HealthRecord, user: User) -> HealthAnalysis:
    """
    Analyze a health record and generate clinical insights.
    Provides BMI, blood pressure, hemoglobin, glucose status + corrective feedback.
    """
    corrections = []
    alerts = []

    # ── BMI Analysis ──────────────────────────────────────────
    bmi = record.bmi or 0
    if bmi < 18.5:
        bmi_status = "underweight"
        bmi_message = "Your BMI is below normal. Focus on calorie-dense, nutritious foods."
        corrections.append("Increase meal portions with healthy fats like coconut oil and ghee.")
        alerts.append("Low BMI detected – consider consulting your doctor about weight gain goals.")
    elif bmi < 25:
        bmi_status = "normal"
        bmi_message = "Your BMI is in a healthy range. Maintain balanced nutrition."
    elif bmi < 30:
        bmi_status = "overweight"
        bmi_message = "Your BMI is slightly elevated. Focus on fiber-rich meals."
        corrections.append("Reduce fried foods and increase vegetable intake.")
    else:
        bmi_status = "obese"
        bmi_message = "Your BMI indicates obesity. Prioritize low-calorie, nutrient-dense meals."
        corrections.append("Avoid sugary snacks and deep-fried items. Choose steamed or grilled options.")
        alerts.append("High BMI – discuss gestational diabetes risk with your doctor.")

    # ── Weight Gain Analysis (trimester-specific) ─────────────
    if user.pre_pregnancy_weight_kg and record.current_weight_kg:
        gain = record.current_weight_kg - user.pre_pregnancy_weight_kg
        week = record.week_number

        # Expected weight gain ranges by week (for normal BMI pre-pregnancy)
        if week <= 13:
            expected_min, expected_max = 0, 2.0
        elif week <= 26:
            expected_min, expected_max = 2.0, 7.0
        else:
            expected_min, expected_max = 7.0, 16.0

        if gain < expected_min:
            weight_status = "low"
            weight_message = f"Weight gain ({gain:.1f} kg) is below expected range. Increase caloric intake."
            corrections.append("Add nutrient-dense snacks between meals – nuts, ragi porridge, fruit smoothies.")
        elif gain > expected_max:
            weight_status = "high"
            weight_message = f"Weight gain ({gain:.1f} kg) exceeds expected range. Monitor portions."
            corrections.append("Replace refined carbs with whole grains. Reduce ghee usage.")
        else:
            weight_status = "normal"
            weight_message = f"Weight gain ({gain:.1f} kg) is within healthy range."
    else:
        weight_status = "normal"
        weight_message = "Pre-pregnancy weight not recorded. Please update your profile for accurate tracking."

    # ── Blood Pressure Analysis ──────────────────────────────
    if record.blood_pressure_sys and record.blood_pressure_dia:
        sys, dia = record.blood_pressure_sys, record.blood_pressure_dia
        if sys >= 140 or dia >= 90:
            bp_status = "high"
            bp_message = f"Blood pressure ({sys:.0f}/{dia:.0f}) is elevated. Reduce salt intake immediately."
            corrections.append("Avoid pickles, pappadams, and salted snacks. Use herbs for flavoring.")
            alerts.append("HIGH BP – Risk of preeclampsia. Seek medical attention.")
        elif sys >= 120 or dia >= 80:
            bp_status = "elevated"
            bp_message = f"Blood pressure ({sys:.0f}/{dia:.0f}) is slightly elevated. Monitor sodium intake."
            corrections.append("Limit salt to 5g/day. Increase potassium-rich foods like bananas and coconut water.")
        else:
            bp_status = "normal"
            bp_message = f"Blood pressure ({sys:.0f}/{dia:.0f}) is normal."
    else:
        bp_status = "normal"
        bp_message = "Blood pressure not recorded. Please submit readings for monitoring."

    # ── Hemoglobin Analysis ──────────────────────────────────
    if record.hemoglobin:
        hb = record.hemoglobin
        if hb < 7:
            hb_status = "low"
            hb_message = f"Hemoglobin ({hb} g/dL) is critically low – severe anemia."
            corrections.append("URGENT: Include iron-rich foods – beetroot, spinach, jaggery, dates. Take prescribed iron supplements.")
            alerts.append("SEVERE ANEMIA – Consult doctor immediately for iron supplementation.")
        elif hb < 11:
            hb_status = "low"
            hb_message = f"Hemoglobin ({hb} g/dL) indicates mild-moderate anemia."
            corrections.append("Add iron-rich foods: moringa leaves, ragi, liver, green leafy vegetables with vitamin C for absorption.")
        else:
            hb_status = "normal"
            hb_message = f"Hemoglobin ({hb} g/dL) is in a healthy range."
    else:
        hb_status = "normal"
        hb_message = "Hemoglobin not recorded. Please submit lab results for anemia monitoring."

    # ── Blood Sugar Analysis ─────────────────────────────────
    if record.blood_sugar_fasting:
        bs = record.blood_sugar_fasting
        if bs >= 126:
            bs_status = "high"
            bs_message = f"Fasting blood sugar ({bs} mg/dL) is high – possible gestational diabetes."
            corrections.append("Avoid white rice, maida, and sugary drinks. Switch to brown rice and millet-based meals.")
            alerts.append("HIGH BLOOD SUGAR – Gestational diabetes risk. Consult your doctor.")
        elif bs >= 92:
            bs_status = "high"
            bs_message = f"Fasting blood sugar ({bs} mg/dL) is borderline elevated."
            corrections.append("Reduce refined carbohydrates. Include more fiber and protein in each meal.")
        else:
            bs_status = "normal"
            bs_message = f"Fasting blood sugar ({bs} mg/dL) is normal."
    else:
        bs_status = "normal"
        bs_message = "Blood sugar not recorded. Please submit lab results for GDM screening."

    # ── Trimester-specific alerts ─────────────────────────────
    if record.trimester == 1:
        alerts.append("First trimester: Folic acid (400-800 mcg/day) is critical for neural tube development.")
    elif record.trimester == 2:
        alerts.append("Second trimester: Iron and calcium needs increase significantly. Include dairy and leafy greens.")
    elif record.trimester == 3:
        alerts.append("Third trimester: Increase caloric intake by ~300 cal/day. Focus on DHA/omega-3 for brain development.")

    return HealthAnalysis(
        bmi_status=bmi_status,
        bmi_message=bmi_message,
        weight_gain_status=weight_status,
        weight_gain_message=weight_message,
        bp_status=bp_status,
        bp_message=bp_message,
        hemoglobin_status=hb_status,
        hemoglobin_message=hb_message,
        blood_sugar_status=bs_status,
        blood_sugar_message=bs_message,
        corrections=corrections,
        alerts=alerts,
    )
