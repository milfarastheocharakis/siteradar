"""Overture Maps places -> SiteRadar elements, and merging them with OpenStreetMap businesses.

Overture's places (https://docs.overturemaps.org/guides/places/) are free and open (CDLA Permissive 2.0)
and come mostly from Facebook business pages, so they hold many small businesses OpenStreetMap lacks.
Each place becomes an element shaped like an OpenStreetMap one ("type": "overture"), with OpenStreetMap
tags chosen from its category, so the app scores and groups it like any other business.
"""
import math
import re
import unicodedata
from difflib import SequenceMatcher

MIN_CONFIDENCE = 0.6
# Overture passes on each source's licence. Places from Foursquare are Apache 2.0, which would need its own
# licence and notice files next to the data, so only these are kept (CC0 asks for nothing).
OPEN_LICENCES = {'CDLA-Permissive-2.0', 'CC0-1.0'}

# Overture's detailed category (taxonomy.primary) -> OpenStreetMap tag.
PRIMARY = {
    # food and drink
    'fast_food_restaurant': 'amenity=fast_food', 'food_truck_stand': 'amenity=fast_food', 'sandwich_shop': 'amenity=fast_food',
    'cafe': 'amenity=cafe', 'coffee_shop': 'amenity=cafe', 'tea_room': 'amenity=cafe', 'smoothie_juice_bar': 'amenity=cafe',
    'juice_bar': 'amenity=cafe', 'bubble_tea_shop': 'amenity=cafe', 'internet_cafe': 'amenity=internet_cafe',
    'bar': 'amenity=bar', 'cocktail_bar': 'amenity=bar', 'wine_bar': 'amenity=bar', 'beer_bar': 'amenity=bar', 'lounge': 'amenity=bar',
    'beach_bar': 'amenity=bar', 'sports_bar': 'amenity=bar', 'hookah_bar': 'amenity=bar', 'gastropub': 'amenity=pub', 'pub': 'amenity=pub',
    'tapas_bar': 'amenity=bar', 'dance_club': 'amenity=nightclub', 'night_club': 'amenity=nightclub', 'nightlife_venue': 'amenity=nightclub',
    'bakery': 'shop=bakery', 'ice_cream_shop': 'amenity=ice_cream', 'frozen_yogurt_shop': 'amenity=ice_cream',
    'dessert_shop': 'shop=pastry', 'candy_store': 'shop=confectionery', 'chocolatier': 'shop=chocolate', 'diner': 'amenity=restaurant',
    'delicatessen': 'shop=deli', 'caterer': 'craft=caterer',
    'grocery_store': 'shop=supermarket', 'supermarket': 'shop=supermarket', 'convenience_store': 'shop=convenience',
    'butcher_shop': 'shop=butcher', 'liquor_store': 'shop=alcohol', 'tobacco_shop': 'shop=tobacco', 'health_food_store': 'shop=health_food',
    'organic_grocery_store': 'shop=health_food', 'fishmonger': 'shop=seafood', 'cheese_shop': 'shop=cheese', 'produce_store': 'shop=greengrocer',
    'wine_store': 'shop=wine', 'beverage_store': 'shop=beverages', 'food_and_beverage_store': 'shop=food',
    'winery': 'craft=winery', 'brewery': 'craft=brewery', 'distillery': 'craft=distillery',
    # stays
    'hotel': 'tourism=hotel', 'resort': 'tourism=hotel', 'boutique_hotel': 'tourism=hotel', 'motel': 'tourism=motel',
    'holiday_rental_home': 'tourism=apartment', 'service_apartment': 'tourism=apartment', 'cottage': 'tourism=chalet', 'cabin': 'tourism=chalet',
    'lodging': 'tourism=guest_house', 'lodge': 'tourism=guest_house', 'guest_house': 'tourism=guest_house', 'bed_and_breakfast': 'tourism=guest_house',
    'inn': 'tourism=guest_house', 'hostel': 'tourism=hostel', 'campground': 'tourism=camp_site', 'rv_park': 'tourism=caravan_site',
    # shops
    'shoe_store': 'shop=shoes', 'jewelry_store': 'shop=jewelry', 'watch_store': 'shop=watches', 'eyewear_and_optician': 'shop=optician',
    'electronics_store': 'shop=electronics', 'mobile_phone_store': 'shop=mobile_phone', 'computer_store': 'shop=computer', 'appliance_store': 'shop=appliance',
    'hardware_store': 'shop=hardware', 'furniture_store': 'shop=furniture', 'home_goods_store': 'shop=houseware', 'garden_center': 'shop=garden_centre',
    'kitchen_and_bath_store': 'shop=kitchen', 'lighting_store': 'shop=lighting', 'paint_store': 'shop=paint', 'flooring_store': 'shop=flooring',
    'mattress_store': 'shop=bed', 'home_improvement_store': 'shop=doityourself', 'building_supply_store': 'shop=trade',
    'florist': 'shop=florist', 'flowers_and_gifts_store': 'shop=gift', 'gift_shop': 'shop=gift', 'souvenir_store': 'shop=gift',
    'bookstore': 'shop=books', 'music_store': 'shop=music', 'newsstand': 'shop=newsagent', 'books_music_and_video_store': 'shop=books',
    'cosmetics_and_beauty_supply': 'shop=cosmetics', 'perfume_store': 'shop=perfumery', 'personal_care_and_beauty_store': 'shop=cosmetics',
    'arts_crafts_and_hobby_store': 'shop=craft', 'sporting_goods_store': 'shop=sports', 'toys_and_games_store': 'shop=toys',
    'animal_and_pet_store': 'shop=pet', 'pet_store': 'shop=pet', 'office_supply_store': 'shop=stationery',
    'musical_instrument_and_pro_audio_store': 'shop=musical_instrument', 'department_store': 'shop=department_store',
    'second_hand_store': 'shop=second_hand', 'discount_store': 'shop=variety_store', 'warehouse_club_store': 'shop=wholesale', 'superstore': 'shop=supermarket',
    'smoke_and_vape_store': 'shop=e-cigarette', 'medical_supply_store': 'shop=medical_supply', 'party_supply_store': 'shop=party',
    'outlet_store': 'shop=clothes', 'duty_free_store': 'shop=gift', 'trophy_store': 'shop=trophy',
    'vehicle_parts_store': 'shop=car_parts', 'car_dealer': 'shop=car', 'auto_dealer': 'shop=car', 'used_car_dealer': 'shop=car',
    'motorcycle_dealer': 'shop=motorcycle', 'boat_dealer': 'shop=boat', 'vehicle_dealer': 'shop=car',
    'pharmacy': 'amenity=pharmacy', 'drugstore': 'shop=chemist', 'pharmacy_and_drug_store': 'amenity=pharmacy',
    'shopping': 'shop=yes', 'specialty_store': 'shop=yes',
    # beauty and wellness
    'beauty_salon': 'shop=beauty', 'hair_salon': 'shop=hairdresser', 'barber': 'shop=hairdresser', 'nail_salon': 'shop=beauty',
    'tattoo_and_piercing': 'shop=tattoo', 'skin_care_and_makeup': 'shop=beauty', 'makeup_artist': 'shop=beauty', 'laser_hair_removal': 'shop=beauty',
    'tanning_salon': 'leisure=tanning_salon', 'shoe_repair': 'shop=shoe_repair', 'personal_or_beauty_service': 'shop=beauty',
    'spa': 'leisure=spa', 'day_spa': 'leisure=spa', 'health_spa': 'leisure=spa', 'massage_therapy': 'shop=massage', 'massage': 'shop=massage',
    'nutrition_service': 'healthcare=nutrition_counselling', 'wellness_service': 'leisure=spa',
    'gym': 'leisure=fitness_centre', 'fitness_studio': 'leisure=fitness_centre', 'yoga_studio': 'leisure=fitness_centre',
    'pilates_studio': 'leisure=fitness_centre', 'boxing_gym': 'leisure=fitness_centre', 'sport_or_fitness_facility': 'leisure=fitness_centre',
    'martial_arts_club': 'leisure=sports_centre', 'go_kart_club': 'leisure=sports_centre', 'dance_school': 'amenity=dancing_school',
    # offices and services
    'advertising_agency': 'office=advertising_agency', 'marketing_agency': 'office=advertising_agency',
    'internet_marketing_service': 'office=advertising_agency', 'media_agency': 'office=advertising_agency',
    'employment_agency': 'office=employment_agency', 'business_consulting': 'office=consulting', 'professional_service': 'office=company',
    'accountant': 'office=accountant', 'insurance_agency': 'office=insurance', 'financial_advising': 'office=financial_advisor',
    'financial_service': 'office=financial', 'currency_exchange': 'amenity=bureau_de_change', 'appraisal_service': 'office=company',
    'real_estate_investment': 'office=estate_agent', 'real_estate_service': 'office=estate_agent', 'real_estate_agent': 'office=estate_agent',
    'attorney_or_law_firm': 'office=lawyer', 'lawyer': 'office=lawyer', 'legal_service': 'office=lawyer', 'notary_public': 'office=notary',
    'architectural_designer': 'office=architect', 'graphic_designer': 'office=graphic_design', 'web_designer': 'office=it', 'sign_making': 'craft=signmaker',
    'engineering_service': 'office=engineer', 'event_photography_service': 'craft=photographer', 'photographer': 'craft=photographer',
    'broadcasting_media_production': 'amenity=studio', 'music_production': 'amenity=studio', 'movie_television_studio': 'amenity=studio',
    'publisher': 'office=publisher', 'print_media': 'office=publisher',
    'it_service_and_computer_repair': 'shop=computer_repair', 'computer_hardware_company': 'shop=computer', 'software_development': 'office=it',
    'information_technology_company': 'office=it', 'internet_service_provider': 'office=telecommunication', 'telecommunications_company': 'office=telecommunication',
    'party_and_event_planning': 'office=event_management', 'wedding_planning': 'office=event_management', 'kids_recreation_and_party': 'office=event_management',
    'boat_charter': 'amenity=boat_rental', 'boat_tour': 'amenity=boat_rental', 'boat_rental': 'amenity=boat_rental',
    'travel_agent': 'shop=travel_agency', 'tour_operator': 'shop=travel_agency', 'sightseeing_tour_agency': 'shop=travel_agency',
    'bus_tour': 'shop=travel_agency', 'food_tour': 'shop=travel_agency', 'art_tour': 'shop=travel_agency', 'travel_service': 'shop=travel_agency',
    'travel_company': 'shop=travel_agency', 'luggage_storage': 'shop=storage_rental',
    'car_rental_service': 'amenity=car_rental', 'car_rental_agency': 'amenity=car_rental', 'bus_rental': 'amenity=car_rental',
    'rv_rental_service': 'amenity=car_rental', 'motorcycle_rental_service': 'amenity=motorcycle_rental', 'bike_rental': 'amenity=bicycle_rental',
    'rental_service': 'shop=rental', 'recreational_equipment_rental': 'shop=rental',
    'shipping_or_delivery_service': 'office=logistics', 'taxi_or_ride_share_service': 'office=taxi', 'printing_service': 'shop=copyshop',
    'laundry_service': 'shop=laundry', 'dry_cleaning': 'shop=dry_cleaning', 'storage_facility': 'shop=storage_rental',
    'telecommunications_service': 'shop=mobile_phone', 'funeral_service': 'shop=funeral_directors',
    'day_care_preschool': 'amenity=childcare', 'child_care_and_day_care': 'amenity=childcare',
    'veterinarian': 'amenity=veterinary', 'pet_groomer': 'shop=pet_grooming', 'dog_trainer': 'shop=pet', 'pet_sitting': 'shop=pet', 'pet_breeder': 'shop=pet',
    'agricultural_service': 'shop=agrarian', 'farm': 'shop=farm', 'dairy_farm': 'shop=farm', 'urban_farm': 'shop=farm', 'food_and_drink': 'shop=farm',
    'hotel_supply_service': 'shop=wholesale', 'food_beverage_distributor': 'shop=wholesale', 'restaurant_equipment_and_supply': 'shop=wholesale',
    'supplier_or_distributor': 'shop=wholesale', 'wholesaler': 'shop=wholesale',
    # trades
    'carpenter': 'craft=carpenter', 'hvac_service': 'craft=hvac', 'contractor': 'craft=builder', 'home_security': 'shop=security',
    'pest_control_service': 'craft=pest_control', 'interior_design': 'shop=interior_decoration', 'key_and_locksmith': 'shop=locksmith',
    'home_cleaning': 'craft=cleaning', 'windows_installation': 'craft=window_construction', 'fireplace_service': 'shop=fireplace',
    'plumbing': 'craft=plumber', 'plumber': 'craft=plumber', 'electrician': 'craft=electrician', 'painting': 'craft=painter', 'roofing': 'craft=roofer',
    'landscaping': 'craft=gardener', 'gardener': 'craft=gardener', 'pool_cleaning': 'shop=swimming_pool', 'home_service': 'craft=yes',
    'building_or_construction_service': 'craft=builder', 'stone_and_masonry': 'craft=stonemason',
    'machine_shop': 'craft=metal_construction', 'metal_fabricator': 'craft=metal_construction', 'commercial_refrigeration': 'craft=hvac',
    'elevator_service': 'craft=yes', 'bike_repair_maintenance': 'shop=bicycle', 'jewelry_and_watches_manufacturer': 'craft=jeweller',
    'furniture_manufacturer': 'craft=cabinet_maker', 'glass_manufacturer': 'craft=glaziery', 'manufacturer': 'craft=yes',
    'industrial_equipment_manufacturer': 'craft=yes', 'mattress_manufacturing': 'craft=upholsterer', 'textile_manufacturer': 'craft=yes',
    'apparel_manufacturer': 'craft=tailor', 'commercial_industrial': 'office=company', 'industrial_company': 'office=company',
    'agricultural_cooperative': 'office=cooperative', 'agriculture': 'shop=agrarian', 'corporate_or_business_office': 'office=company',
    'automotive_repair': 'shop=car_repair', 'automotive_service': 'shop=car_repair', 'tire_dealer_and_repair': 'shop=tyres',
    'auto_detailing': 'amenity=car_wash', 'car_wash': 'amenity=car_wash', 'auto_body_shop': 'shop=car_repair', 'auto_glass_service': 'shop=car_repair',
    'towing_service': 'shop=car_repair', 'auto_customization': 'shop=car_repair', 'auto_restoration_service': 'shop=car_repair',
    'motorcycle_repair': 'shop=motorcycle_repair', 'boat_service': 'shop=boat',
    # health
    'dentist': 'amenity=dentist', 'dental_clinic': 'amenity=dentist', 'doctor': 'amenity=doctors', 'general_practitioner': 'amenity=doctors',
    'primary_care_or_general_clinic': 'amenity=doctors', 'pediatric_clinic': 'amenity=doctors', 'specialized_health_care': 'amenity=doctors',
    'medical_service': 'amenity=doctors', 'outpatient_care_facility': 'amenity=clinic', 'surgery': 'amenity=clinic',
    'specialized_medical_facility': 'amenity=clinic', 'reproductive_perinatal_and_womens_care': 'amenity=doctors',
    'physical_medicine_and_rehabilitation': 'healthcare=physiotherapist', 'physical_therapy': 'healthcare=physiotherapist',
    'behavioral_or_mental_health_clinic': 'healthcare=psychotherapist', 'psychologist': 'healthcare=psychotherapist',
    'diagnostics_imaging_or_lab_service': 'healthcare=laboratory', 'vision_or_eye_care_clinic': 'healthcare=optometrist',
    'optometrist': 'healthcare=optometrist', 'complementary_and_alternative_medicine': 'healthcare=alternative', 'health_care': 'healthcare=yes',
    # learning and leisure businesses
    'language_school': 'amenity=language_school', 'driving_school': 'amenity=driving_school', 'music_school': 'amenity=music_school',
    'art_school': 'amenity=training', 'cooking_school': 'amenity=training', 'cosmetology_school': 'amenity=training',
    'computer_coaching': 'amenity=training', 'vocational_and_technical_school': 'amenity=training', 'specialty_school': 'amenity=training',
    'tutoring_service': 'amenity=prep_school', 'educational_service': 'amenity=prep_school', 'education': 'amenity=prep_school',
    'private_school': 'amenity=prep_school', 'class_venue': 'amenity=training', 'arts_and_crafts_space': 'amenity=training',
    'event_venue': 'amenity=events_venue', 'music_venue': 'amenity=events_venue', 'theatre_venue': 'amenity=theatre',
    'performing_arts_venue': 'amenity=theatre', 'movie_theater': 'amenity=cinema', 'arcade': 'leisure=amusement_arcade',
    'gaming_venue': 'amenity=internet_cafe', 'golf_course': 'leisure=golf_course', 'art_gallery': 'tourism=gallery',
    # kinds Crete has many of that the broad categories label badly
    'clothing_store': 'shop=clothes', 'fashion_boutique': 'shop=boutique', 'fashion_accessories_store': 'shop=fashion_accessories',
    'eyewear_store': 'shop=optician', 'bike_store': 'shop=bicycle', 'toy_store': 'shop=toys', 'fabric_store': 'shop=fabric',
    'carpet_store': 'shop=carpet', 'nursery_and_gardening_store': 'shop=garden_centre', 'musical_instrument_store': 'shop=musical_instrument',
    'auto_parts_store': 'shop=car_parts', 'beauty_supply_store': 'shop=cosmetics', 'antique_store': 'shop=antiques', 'pawn_shop': 'shop=pawnbroker',
    'laundromat': 'shop=laundry', 'property_management': 'office=property_management', 'taxi_service': 'office=taxi',
    'dance_studio': 'leisure=dance', 'escape_room': 'leisure=escape_game', 'miniature_golf_course': 'leisure=miniature_golf',
    'horseback_riding_service': 'leisure=horse_riding', 'equestrian_facility': 'leisure=horse_riding',
    'scuba_diving_center': 'amenity=dive_centre', 'scuba_diving_instruction': 'amenity=dive_centre', 'diving_center': 'amenity=dive_centre',
    'doctors_office': 'amenity=doctors', 'family_practice': 'amenity=doctors', 'orthodontics': 'amenity=dentist', 'cosmetic_dentistry': 'amenity=dentist',
    'speech_therapy': 'healthcare=speech_therapist', 'occupational_therapy': 'healthcare=occupational_therapist', 'podiatry': 'healthcare=podiatrist',
    'psychology': 'healthcare=psychotherapist', 'psychotherapy': 'healthcare=psychotherapist', 'counseling': 'healthcare=psychotherapist',
}
# Broad category (basic_category) -> tag, when the detailed one isn't listed above.
BASIC = {
    'restaurant': 'amenity=restaurant', 'casual_eatery': 'amenity=restaurant', 'food_service': 'amenity=restaurant',
    'fashion_and_apparel_store': 'shop=clothes', 'hardware_home_and_garden_store': 'shop=hardware', 'private_lodging': 'tourism=apartment',
    'b2b_service': 'office=company', 'design_service': 'office=company', 'media_service': 'office=company', 'technical_service': 'craft=yes',
    'event_or_party_service': 'office=event_management', 'family_service': 'amenity=childcare', 'animal_or_pet_service': 'shop=pet',
    'vehicle_service': 'shop=car_repair', 'sport_or_recreation_club': 'leisure=sports_centre', 'specialty_school': 'amenity=training',
}
# Kinds that are not businesses to sell a website to: public bodies, places, landmarks, chains of cash machines...
SKIP = {
    'beach', 'historic_site', 'geographic_entities', 'mountain', 'river', 'lake', 'island', 'forest', 'waterfall', 'land_feature',
    'hot_springs', 'nature_reserve', 'national_park', 'park', 'garden', 'dog_park', 'playground', 'public_plaza', 'public_fountain',
    'monument', 'sculpture_statue', 'castle', 'fort', 'christian_place_of_worship', 'muslim_place_of_worship', 'jewish_place_of_worship',
    'place_of_worship', 'religious_organization', 'government_office', 'government_department', 'community_and_government', 'courthouse',
    'police_station', 'fire_station', 'embassy', 'military_site', 'library', 'community_center', 'cultural_center', 'museum',
    'social_or_community_service', 'civic_organization', 'political_organization', 'labor_union', 'youth_organization', 'social_club',
    'sport_league', 'sport_team', 'stadium_arena', 'sport_field', 'sport_court', 'swimming_pool', 'recreational_trail_or_path',
    'elementary_school', 'middle_school', 'high_school', 'preschool', 'college_university', 'campus_building', 'educational_facility',
    'public_school', 'research_institute', 'medical_school', 'hospital', 'emergency_department', 'senior_living_facility',
    'atm', 'bank_or_credit_union', 'money_transfer_service', 'gas_station', 'fueling_station', 'ev_charging_station', 'parking',
    'airport', 'air_transport_facility_or_service', 'public_transit_facility_or_service', 'train_station', 'ferry_service', 'bridge', 'pier',
    'lighthouse', 'marina', 'public_utility', 'water_utility_provider', 'electric_utility_provider', 'condominium', 'apartment',
    'shopping_mall', 'farmers_market', 'casino', 'adult_entertainment_venue', 'zoo', 'aquarium', 'animal_attraction', 'animal_shelter',
    'adoption_service', 'amusement_park', 'psychic_advising', 'radio_station', 'visitor_center', 'arts_and_entertainment',
    'sports_and_recreation', 'travel_and_transportation', 'school', 'laboratory', 'package_locker', 'post_office', 'recycling_center',
}
# Public schools, kindergartens, councils and associations that slip in under business kinds.
PUBLIC_NAME = re.compile(
    r'(δημοτικ[οό] σχολε[ιί]ο|γυμν[αά]σιο|λ[υύ]κειο|νηπιαγωγε[ιί]ο|πανεπιστ[ηή]μιο|δ[ηή]μος |περιφ[εέ]ρεια|ιερ[οό]ς να[οό]ς|'
    r'εκκλησ[ιί]α|μοναστ[ηή]ρι|μον[ηή] |σ[υύ]λλογος|σωματε[ιί]ο|ε\.?κ\.?φ\.?ε|κ\.?δ\.?α\.?π|σχολικ[οό] [εέ]τος|'
    r'public school|primary school|high school|kindergarten|municipality|university)', re.I)


def tags_for(basic, primary, name):
    """OpenStreetMap tags for an Overture place, or None when it isn't a business SiteRadar lists.
    The tags carry "overture:category" when the OpenStreetMap tag says less than Overture's own kind,
    so the app can show "Donut shop" instead of "Restaurant"."""
    if basic in SKIP or primary in SKIP or not basic or PUBLIC_NAME.search(name or ''):
        return None
    tag = PRIMARY.get(primary)
    exact = bool(tag)
    tags = {}
    if not tag and primary and primary.endswith('_restaurant'):
        tag, exact = 'amenity=restaurant', True
        cuisine = primary[:-len('_restaurant')]
        if cuisine not in ('casual', 'family', 'fine_dining', 'buffet', 'theme'):
            tags['cuisine'] = cuisine
    if not tag:
        tag = PRIMARY.get(basic) or BASIC.get(basic)
    if not tag:
        return None
    k, v = tag.split('=')
    tags[k] = v
    if primary and (not exact or v in ('yes', 'company')):
        tags['overture:category'] = primary
    return tags


GREEK = dict(zip('αβγδεζηθικλμνξοπρσςτυφχψω', ['a', 'v', 'g', 'd', 'e', 'z', 'i', 'th', 'i', 'k', 'l', 'm', 'n', 'x', 'o', 'p', 'r', 's', 's', 't', 'y', 'f', 'ch', 'ps', 'o']))
FILLER = re.compile(r'\b(the|and|of|ο|η|το|οι|τα|του|της|των|και|ike|epe|oe|ee|ae|abee|aebe|ltd|cafe|caffe|coffee|bar|restaurant|taverna|tavern|hotel|apartments|studios|rooms|villa|villas)\b')


def name_key(name):
    """A loose spelling of a name that matches across Greek and Latin letters and accents."""
    s = unicodedata.normalize('NFD', str(name or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = ''.join(GREEK.get(c, c) for c in s)
    s = s.replace('ou', 'u').replace('mp', 'b').replace('nt', 'd').replace('gk', 'g').replace('ch', 'h').replace('y', 'i').replace('w', 'o')
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = FILLER.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def same_name(a, b):
    if not a or not b:
        return False
    if a == b or (min(len(a), len(b)) >= 5 and (a in b or b in a)):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def phone_key(p):
    d = re.sub(r'\D', '', str(p or ''))
    return d[-10:] if len(d) >= 8 else ''


def km(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    a = math.sin((lat2 - lat1) * r / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


SOCIAL = [('facebook.com', 'contact:facebook'), ('fb.com', 'contact:facebook'), ('instagram.com', 'contact:instagram'),
          ('tiktok.com', 'contact:tiktok'), ('youtube.com', 'contact:youtube'), ('linkedin.com', 'contact:linkedin'), ('twitter.com', 'contact:twitter'), ('x.com', 'contact:twitter')]


def open_licence(source):
    lic = (source or {}).get('license')
    return lic in OPEN_LICENCES if lic else (source or {}).get('dataset') != 'Foursquare'


def datasets_of(place):
    """The providers behind a place, such as meta or Microsoft (Overture's own confidence score left out)."""
    return {s.get('dataset') for s in place.get('sources') or [] if s and s.get('dataset') and s.get('dataset') != 'Overture'}


def element_from(place):
    """A SiteRadar element for one Overture place row (a dict from the places parquet), or None."""
    if place.get('operating_status') not in (None, 'open'):
        return None
    if not all(open_licence(s) for s in place.get('sources') or []):
        return None
    if (place.get('confidence') or 0) < MIN_CONFIDENCE:
        return None
    name = ((place.get('names') or {}).get('primary') or '').strip()
    if not name:
        return None
    tax = place.get('taxonomy') or {}
    tags = tags_for(place.get('basic_category'), tax.get('primary'), name)
    if not tags:
        return None
    box = place.get('bbox') or {}
    lat, lon = box.get('ymin'), box.get('xmin')
    if lat is None or lon is None:
        return None
    out = {'name': name}
    out.update(tags)
    phones = [p for p in (place.get('phones') or []) if p][:3]
    if phones:
        out['phone'] = ';'.join(phones)
    sites = [w for w in (place.get('websites') or []) if w]
    if sites:
        out['website'] = sites[0]
    for url in place.get('socials') or []:
        host = re.sub(r'^https?://(www\.|m\.)?', '', str(url).lower()).split('/')[0]
        for domain, key in SOCIAL:
            if host == domain or host.endswith('.' + domain):
                out.setdefault(key, url)
                break
    emails = [e for e in (place.get('emails') or []) if e]
    if emails:
        out['email'] = emails[0]
    addr = (place.get('addresses') or [None])[0] or {}
    if addr.get('freeform'):
        out['addr:street'] = addr['freeform']
    if addr.get('locality'):
        out['addr:city'] = addr['locality']
    if addr.get('postcode'):
        out['addr:postcode'] = addr['postcode']
    brand = place.get('brand') or {}
    if brand.get('wikidata'):
        out['brand:wikidata'] = brand['wikidata']
    if (brand.get('names') or {}).get('primary'):
        out['brand'] = brand['names']['primary']
    return {'type': 'overture', 'id': place['id'], 'lat': round(lat, 7), 'lon': round(lon, 7), 'tags': out}


WEB_KEYS = ('website', 'contact:website', 'url')

CDLA_TEXT = """Community Data License Agreement - Permissive - Version 2.0

This is the Community Data License Agreement - Permissive, Version 2.0 (the "agreement"). Data Provider(s) and Data Recipient(s) agree as follows:

1. Provision of the Data

1.1. A Data Recipient may use, modify, and share the Data made available by Data Provider(s) under this agreement if that Data Recipient follows the terms of this agreement.

1.2. This agreement does not impose any restriction on a Data Recipient's use, modification, or sharing of any portions of the Data that are in the public domain or that may be used, modified, or shared under any other legal exception or limitation.

2. Conditions for Sharing Data

2.1. A Data Recipient may share Data, with or without modifications, so long as the Data Recipient makes available the text of this agreement with the shared Data.

3. No Restrictions on Results

3.1. This agreement does not impose any restriction or obligations with respect to the use, modification, or sharing of Results.

4. No Warranty; Limitation of Liability

4.1. All Data Recipients receive the Data subject to the following terms:

THE DATA IS PROVIDED ON AN "AS IS" BASIS, WITHOUT REPRESENTATIONS, WARRANTIES OR CONDITIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED INCLUDING, WITHOUT LIMITATION, ANY WARRANTIES OR CONDITIONS OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.

NO DATA PROVIDER SHALL HAVE ANY LIABILITY FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING WITHOUT LIMITATION LOST PROFITS), HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE DATA OR RESULTS, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

5. Definitions

5.1. "Data" means the material received by a Data Recipient under this agreement.

5.2. "Data Provider" means any person who is the source of Data provided under this agreement and in reliance on a Data Recipient's agreement to its terms.

5.3. "Data Recipient" means any person who receives Data directly or indirectly from a Data Provider and agrees to the terms of this agreement.

5.4. "Results" means any outcome obtained by computational analysis of Data, including for example machine learning models and models' insights.
"""
PROVIDER_NAMES = {'meta': 'Meta', 'Microsoft': 'Microsoft', 'AllThePlaces': 'AllThePlaces', 'Uberall': 'Uberall', 'PinMeTo': 'PinMeTo',
                  'OpenTravel': 'OpenTravel', 'DAC': 'DAC', 'BrightQuery': 'BrightQuery'}


def licence_text(release=None, datasets=()):
    """The notice that goes next to the data files: where the data comes from and under which licences."""
    text = """Where this data comes from

OpenStreetMap: the businesses with "type": "node", "way" or "relation", and every municipality boundary.
© OpenStreetMap contributors. Available under the Open Database License (ODbL) 1.0:
https://www.openstreetmap.org/copyright and https://opendatacommons.org/licenses/odbl/1-0/
"""
    if not release:
        return text
    names = sorted(PROVIDER_NAMES.get(d, d) for d in datasets)
    who = ', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else (names[0] if names else 'its providers')
    return text + f"""
Overture Maps, release {release}: the businesses with "type": "overture", and the websites, social pages,
phones and emails taken from Overture for OpenStreetMap businesses (those carry an "overture:id" tag).
Data from {who}, through the Overture Maps Foundation (https://overturemaps.org,
https://docs.overturemaps.org/attribution/). Available under the Community Data License Agreement
Permissive 2.0, whose text follows; AllThePlaces data is under CC0 1.0. The data was changed to
SiteRadar's format and merged with OpenStreetMap.


{CDLA_TEXT}"""


def merge(osm, overture):
    """Overture elements that OpenStreetMap doesn't have yet. When both have a business (a close name within
    150 m, or the same phone within 300 m), the OpenStreetMap copy stays and takes the website, social pages,
    phone and email it was missing from Overture. Returns (new Overture elements, number merged)."""
    grid = {}
    def cell(lat, lon):
        return (math.floor(lat * 200), math.floor(lon * 200))  # about 500 m by 450 m
    for el in osm:
        lat, lon = el.get('lat', el.get('center', {}).get('lat')), el.get('lon', el.get('center', {}).get('lon'))
        el['_k'] = name_key(el['tags'].get('name'))
        el['_p'] = {phone_key(p) for p in re.split(r'[;,]', el['tags'].get('phone', '') + ';' + el['tags'].get('contact:phone', ''))} - {''}
        el['_at'] = (lat, lon)
        grid.setdefault(cell(lat, lon), []).append(el)
    fresh, merged = [], 0
    for ov in overture:
        lat, lon = ov['lat'], ov['lon']
        key = name_key(ov['tags']['name'])
        phones = {phone_key(p) for p in ov['tags'].get('phone', '').split(';')} - {''}
        a, o = cell(lat, lon)
        twin = None
        for da in (-1, 0, 1):
            for do in (-1, 0, 1):
                for el in grid.get((a + da, o + do), []):
                    d = km(lat, lon, *el['_at'])
                    if (d <= 0.15 and same_name(key, el['_k'])) or (d <= 0.3 and phones & el['_p']):
                        twin = el
                        break
                if twin:
                    break
            if twin:
                break
        if not twin:
            fresh.append(ov)
            continue
        merged += 1
        t, src = twin['tags'], ov['tags']
        if not any(t.get(k) for k in WEB_KEYS) and src.get('website'):
            t['website'] = src['website']
        for k in ('contact:facebook', 'contact:instagram', 'contact:tiktok', 'contact:youtube', 'contact:linkedin', 'contact:twitter', 'email'):
            if src.get(k) and not t.get(k) and not (k == 'contact:facebook' and t.get('facebook')) and not (k == 'contact:instagram' and t.get('instagram')):
                t[k] = src[k]
        if src.get('phone') and not (t.get('phone') or t.get('contact:phone')):
            t['phone'] = src['phone']
        t.setdefault('overture:id', ov['id'])
    for el in osm:
        for k in ('_k', '_p', '_at'):
            el.pop(k, None)
    return fresh, merged
