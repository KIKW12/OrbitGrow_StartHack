"""
Greenhouse data models — crop definitions, greenhouse state builders,
astronaut profiles, and Mars environment constants.
"""

# ---------------------------------------------------------------------------
# Crop definitions
# ---------------------------------------------------------------------------

CROPS = {
    "potato": {
        "id": "potato", "name": "Potato", "emoji": "🥔",
        "growth_cycle": 120,
        "max_typical_yield": 6.0, "min_typical_yield": 3.5,
        "max_temperature": 28.0, "min_temperature": 15.0,
        "max_humidity": 85.0, "min_humidity": 60.0,
        "max_light": 600.0, "min_light": 200.0,
        "max_ph": 7.0, "min_ph": 5.5,
        "max_soil_moisture": 0.45, "min_soil_moisture": 0.25,
        "calories": 77.0, "carbohydrate": 17.0, "protein": 2.0, "fat": 0.1,
        "vitamin_a": 0.0, "vitamin_c": 19.7, "vitamin_k": 2.9,
        "description": "High-calorie staple. Long 120-Sol cycle but highest yield per m².",
    },
    "beans": {
        "id": "beans", "name": "Beans", "emoji": "🫘",
        "growth_cycle": 65,
        "max_typical_yield": 2.5, "min_typical_yield": 1.2,
        "max_temperature": 30.0, "min_temperature": 18.0,
        "max_humidity": 80.0, "min_humidity": 50.0,
        "max_light": 700.0, "min_light": 300.0,
        "max_ph": 7.5, "min_ph": 6.0,
        "max_soil_moisture": 0.40, "min_soil_moisture": 0.20,
        "calories": 347.0, "carbohydrate": 63.0, "protein": 21.0, "fat": 1.2,
        "vitamin_a": 0.0, "vitamin_c": 4.0, "vitamin_k": 19.0,
        "description": "Primary protein source. Nitrogen-fixing roots improve soil.",
    },
    "lettuce": {
        "id": "lettuce", "name": "Lettuce", "emoji": "🥬",
        "growth_cycle": 35,
        "max_typical_yield": 4.0, "min_typical_yield": 2.0,
        "max_temperature": 24.0, "min_temperature": 10.0,
        "max_humidity": 80.0, "min_humidity": 50.0,
        "max_light": 500.0, "min_light": 150.0,
        "max_ph": 7.0, "min_ph": 6.0,
        "max_soil_moisture": 0.50, "min_soil_moisture": 0.30,
        "calories": 15.0, "carbohydrate": 2.9, "protein": 1.4, "fat": 0.2,
        "vitamin_a": 166.0, "vitamin_c": 9.2, "vitamin_k": 102.6,
        "description": "Fastest cycle (35 Sol). Critical Vitamin A and K source.",
    },
    "radish": {
        "id": "radish", "name": "Radish", "emoji": "🌱",
        "growth_cycle": 30,
        "max_typical_yield": 5.0, "min_typical_yield": 2.5,
        "max_temperature": 22.0, "min_temperature": 5.0,
        "max_humidity": 80.0, "min_humidity": 45.0,
        "max_light": 600.0, "min_light": 200.0,
        "max_ph": 7.0, "min_ph": 5.8,
        "max_soil_moisture": 0.40, "min_soil_moisture": 0.20,
        "calories": 16.0, "carbohydrate": 3.4, "protein": 0.7, "fat": 0.1,
        "vitamin_a": 0.0, "vitamin_c": 14.7, "vitamin_k": 1.3,
        "description": "Fastest harvest (30 Sol). Key Vitamin C contributor.",
    },
    "herbs": {
        "id": "herbs", "name": "Herbs", "emoji": "🌿",
        "growth_cycle": 45,
        "max_typical_yield": 2.0, "min_typical_yield": 0.8,
        "max_temperature": 28.0, "min_temperature": 12.0,
        "max_humidity": 75.0, "min_humidity": 40.0,
        "max_light": 600.0, "min_light": 200.0,
        "max_ph": 7.5, "min_ph": 6.0,
        "max_soil_moisture": 0.35, "min_soil_moisture": 0.15,
        "calories": 40.0, "carbohydrate": 7.0, "protein": 3.3, "fat": 0.8,
        "vitamin_a": 116.0, "vitamin_c": 50.0, "vitamin_k": 200.0,
        "description": "Balanced vitamins A, C, K. Crew morale and flavour.",
    },
}

# Robot dog scan angles per greenhouse (4 positions, fixed route)
SCAN_ANGLES = [
    {"id": "top_down",    "label": "Top Overview",    "angle_deg": 90,  "description": "Full canopy aerial view"},
    {"id": "side_left",   "label": "Row Side View",   "angle_deg": 0,   "description": "Lateral plant profile"},
    {"id": "close_up",    "label": "Leaf Close-up",   "angle_deg": 45,  "description": "Leaf detail — disease detection"},
    {"id": "ground_level","label": "Root Zone",       "angle_deg": -15, "description": "Soil moisture and root health"},
]


def build_initial_greenhouses():
    """Build initial state for 10 greenhouses — 2 per crop (potato, beans, lettuce, radish, herbs)."""
    configs = [
        # id             name                    crop      temp  hum   ph    soil  photo  light  day_offset
        ("gh_potato_1",  "Potato Dome I",        "potato",  22.0, 65.0, 6.5, 0.35, 14.0, 400.0,  0),
        ("gh_potato_2",  "Potato Dome II",       "potato",  22.5, 64.0, 6.4, 0.36, 14.0, 410.0, 30),
        ("gh_beans_1",   "Bean Station I",       "beans",   24.0, 60.0, 6.8, 0.30, 12.0, 500.0,  0),
        ("gh_beans_2",   "Bean Station II",      "beans",   24.5, 61.0, 6.9, 0.31, 12.0, 510.0, 20),
        ("gh_lettuce_1", "Lettuce Lab I",        "lettuce", 20.0, 65.0, 6.5, 0.40, 16.0, 350.0,  0),
        ("gh_lettuce_2", "Lettuce Lab II",       "lettuce", 19.5, 66.0, 6.6, 0.42, 16.0, 360.0, 10),
        ("gh_radish_1",  "Radish Ring I",        "radish",  18.0, 55.0, 6.3, 0.28, 14.0, 420.0,  0),
        ("gh_radish_2",  "Radish Ring II",       "radish",  17.5, 54.0, 6.2, 0.27, 14.0, 430.0, 15),
        ("gh_herbs_1",   "Herb Garden I",        "herbs",   22.0, 58.0, 6.8, 0.25, 13.0, 380.0,  0),
        ("gh_herbs_2",   "Herb Garden II",       "herbs",   22.5, 57.0, 6.7, 0.24, 13.0, 390.0, 22),
    ]

    greenhouses = []
    for gh_id, name, crop_id, temp, humidity, ph, soil, photoperiod, light, day_offset in configs:
        crop = CROPS[crop_id]
        greenhouses.append({
            "id":            gh_id,
            "name":          name,
            "crop_id":       crop_id,
            # Sensors
            "light":         light,
            "photoperiod":   photoperiod,
            "temperature":   temp,
            "air_humidity":  humidity,
            "soil_moisture": soil,
            "day":           float(day_offset),
            "ph":            ph,
            # Health / CV state
            "health":               1.0,
            "disease_detected":     False,
            "stress_flags":         [],
            "last_scan_sol":        -1,
            "cv_confidence":        0.0,
            "latest_scan_results":  [],   # list of {angle_id, health_score, stress_flags, cv_reasoning}
            "alerts":               [],
        })
    return greenhouses


def build_initial_mars_env():
    return {
        "temperature": -60.0,   # °C external
        "light":        400.0,  # µmol/m²/s solar irradiance
    }


def build_initial_facility_env():
    """Shared facility environment (applies to all greenhouses)."""
    return {
        "co2":              1200.0,  # ppm
        "radiation":        0.30,    # relative level (mSv/day equivalent)
        "pressure":        62000.0,  # Pa (Mars ambient ~600; greenhouse maintains ~62 kPa)
        "lighting_energy":  18.0,   # kWh/day total
        "heating_energy":   42.0,   # kWh/day total
        "consumed_water":   120.0,  # L/day total
    }


def build_initial_astronauts():
    return [
        {
            "id": "commander", "name": "Cdr. Chen",
            "min_calories": 2200.0, "consumed_calories": 2200.0,
            "skeletal_muscle_mass_index": 8.5, "body_fat_percentage": 18.0,
        },
        {
            "id": "scientist", "name": "Dr. Osei",
            "min_calories": 2000.0, "consumed_calories": 2000.0,
            "skeletal_muscle_mass_index": 7.8, "body_fat_percentage": 22.0,
        },
        {
            "id": "engineer", "name": "Eng. Vasquez",
            "min_calories": 2400.0, "consumed_calories": 2400.0,
            "skeletal_muscle_mass_index": 9.2, "body_fat_percentage": 16.0,
        },
        {
            "id": "pilot", "name": "Plt. Nakamura",
            "min_calories": 2100.0, "consumed_calories": 2100.0,
            "skeletal_muscle_mass_index": 8.0, "body_fat_percentage": 20.0,
        },
    ]
