import csv
import io
import math
from datetime import datetime, date, timedelta
import calendar
from django.db import transaction
from decimal import Decimal
from .models import (
    Tenant, PlantLookup, AirportLookup, EmissionFactor,
    IngestionJob, RawSourceRecord, NormalizedActivity
)

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees).
    """
    try:
        R = 6371.0  # Earth's radius in kilometers
        lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.asin(math.sqrt(a))
        return round(R * c, 2)
    except Exception:
        return 0.0


def get_days_per_month(start_date, end_date):
    """
    Splits a date range into its component months, returning the days per month
    and the total days in the period.
    """
    total_days = (end_date - start_date).days + 1
    if total_days <= 0:
        total_days = 1
        
    current_date = start_date
    month_days = {}
    
    while current_date <= end_date:
        key = (current_date.year, current_date.month)
        month_days[key] = month_days.get(key, 0) + 1
        current_date += timedelta(days=1)
        
    results = []
    for (year, month), days in month_days.items():
        # Start and end date for this sub-period
        sub_start = max(start_date, date(year, month, 1))
        last_day = calendar.monthrange(year, month)[1]
        sub_end = min(end_date, date(year, month, last_day))
        results.append({
            'year': year,
            'month': month,
            'days': days,
            'start': sub_start,
            'end': sub_end
        })
    return results, total_days


def parse_date(date_str):
    """
    Tolerantly parses dates in multiple common SAP/Utility/Travel formats.
    """
    date_str = date_str.strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y', '%Y%m%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date string: '{date_str}'")


def normalize_sap_unit(unit_str):
    """
    Normalizes inconsistent SAP Units (German & English) to standard system units.
    """
    unit_str = unit_str.upper().strip()
    mapping = {
        'L': 'L', 'LTR': 'L', 'LITER': 'L', 'LITRE': 'L',
        'KG': 'KG', 'KILOGRAMM': 'KG',
        'TO': 'TO', 'TON': 'TO', 'TONNE': 'TO', 'TONS': 'TO',
        'M3': 'M3', 'CUM': 'M3', 'METER3': 'M3', 'KUBIKMETER': 'M3',
        'GAL': 'GAL', 'GALLON': 'GAL', 'GALLONS': 'GAL'
    }
    return mapping.get(unit_str, unit_str)


def parse_sap_csv(tenant, csv_content, file_name):
    """
    Parses SAP material movements flat file exports.
    Expects German headers:
    MANDT, MBLNR, ZEILE, BUDAT, MATNR, MAKTX, MENGE, MEINS, WERKS, LIFNR, DMBTR, WAERS
    """
    job = IngestionJob.objects.create(
        tenant=tenant,
        source_type='SAP',
        file_name=file_name,
        status='SUCCESS'
    )
    
    reader = csv.DictReader(io.StringIO(csv_content))
    # Strip headers in case of spaces
    reader.fieldnames = [name.strip() if name else "" for name in reader.fieldnames]
    
    required_fields = ['MBLNR', 'BUDAT', 'MENGE', 'MEINS', 'WERKS']
    # Check if headers are matching
    missing_headers = [f for f in required_fields if f not in reader.fieldnames]
    if missing_headers:
        job.status = 'FAILED'
        job.notes = f"Missing required SAP headers: {', '.join(missing_headers)}"
        job.save()
        return job, []

    created_activities = []
    row_idx = 0
    success_cnt = 0
    error_cnt = 0

    # Retrieve all emission factors and plants lookup for matching
    efs = {ef.category.lower(): ef for ef in EmissionFactor.objects.all()}
    plants = {p.plant_code.upper(): p for p in tenant.plants.all()}

    for row in reader:
        row_idx += 1
        raw_record = RawSourceRecord.objects.create(
            ingestion_job=job,
            tenant=tenant,
            row_index=row_idx,
            raw_data=row
        )
        
        issues = []
        status = 'PENDING'
        
        try:
            mblnr = row.get('MBLNR')
            budat_str = row.get('BUDAT')
            menge_str = row.get('MENGE')
            meins_str = row.get('MEINS')
            werks_str = row.get('WERKS', '').strip().upper()
            maktx = row.get('MAKTX', '')
            dmbtr_str = row.get('DMBTR', '0')
            waers = row.get('WAERS', 'EUR')

            # Parse Posting Date
            try:
                activity_date = parse_date(budat_str)
            except Exception as e:
                raise ValueError(f"Invalid BUDAT date: {budat_str}")

            # Parse Quantity
            try:
                raw_quantity = Decimal(menge_str.replace(',', '.'))
            except Exception:
                raise ValueError(f"Invalid MENGE quantity: {menge_str}")

            # Parse Spend Amount
            try:
                spend_amount = Decimal(dmbtr_str.replace(',', '.'))
            except Exception:
                spend_amount = Decimal('0')

            # Unit Normalization
            norm_unit = normalize_sap_unit(meins_str)
            qty_multiplier = Decimal('1.0')
            
            # Unit conversions to base emission units (Liters, kg, etc.)
            if norm_unit == 'GAL':
                qty_multiplier = Decimal('3.78541') # Gal to L
                norm_unit = 'L'
                issues.append("Converted quantity from Gallons (GAL) to Liters (L).")
            elif norm_unit == 'TO':
                qty_multiplier = Decimal('1000.0') # Tons to kg
                norm_unit = 'KG'
                issues.append("Converted quantity from Tons (TO) to Kilograms (KG).")

            normalized_qty = raw_quantity * qty_multiplier

            # Plant Code Lookup Verification
            plant_obj = plants.get(werks_str)
            if not plant_obj:
                issues.append(f"Plant code '{werks_str}' not registered in tenant plants directory. Falling back to default region.")
                status = 'FLAGGED'

            # Scope & Category mapping based on Material description / number
            scope = 'Scope 3'
            category = 'Procurement - General'
            ef_category_key = 'procurement - general'
            
            # Determine if it's Fuel (Scope 1) or Goods/Services (Scope 3)
            maktx_upper = maktx.upper()
            if any(k in maktx_upper for k in ['DIESEL', 'HEIZOEL', 'BENZIN', 'FUEL', 'GASOLINE', 'KRAFTSTOFF']):
                scope = 'Scope 1'
                category = 'Fuel - Diesel'
                ef_category_key = 'fuel - diesel'
                if 'GAS' in maktx_upper or 'ERDGAS' in maktx_upper:
                    category = 'Fuel - Natural Gas'
                    ef_category_key = 'fuel - natural gas'
            elif any(k in maktx_upper for k in ['STROM', 'ELECTRICITY', 'POWER', 'ENERGIE']):
                scope = 'Scope 2'
                category = 'Electricity - Purchased'
                ef_category_key = 'electricity - purchased'
            
            # CO2e calculation
            factor_obj = efs.get(ef_category_key)
            if factor_obj:
                factor_val = factor_obj.factor
                co2e = normalized_qty * factor_val
            else:
                # Default fallbacks
                if scope == 'Scope 1':
                    factor_val = Decimal('2.68') # kgCO2e/L diesel
                    co2e = normalized_qty * factor_val
                    issues.append(f"Emission factor for '{category}' not found. Used fallback: {factor_val} kgCO2e/L.")
                else:
                    # Scope 3 Spend based fallback
                    factor_val = Decimal('0.35') # kgCO2e/EUR spent
                    co2e = spend_amount * factor_val
                    issues.append(f"Emission factor not found. Used spend-based fallback: {factor_val} kgCO2e/{waers}.")
                    norm_unit = waers
                    normalized_qty = spend_amount

            # Anomaly Checks
            if normalized_qty <= 0:
                issues.append("Activity quantity is zero or negative.")
                status = 'FLAGGED'
            
            # Spike Detection: if it exceeds 10,000 liters or kg in a single posting
            if normalized_qty > 10000:
                issues.append("Suspiciously high consumption value flagged (>10,000 units).")
                status = 'FLAGGED'

            # Save Normalized Activity
            activity = NormalizedActivity.objects.create(
                tenant=tenant,
                ingestion_job=job,
                raw_record=raw_record,
                scope=scope,
                category=category,
                quantity=normalized_qty,
                unit=norm_unit,
                co2e_kg=co2e,
                start_date=activity_date,
                end_date=activity_date,
                plant_code=werks_str,
                status=status,
                validation_issues=issues,
                original_data={
                    'MBLNR': mblnr,
                    'BUDAT': budat_str,
                    'MENGE': menge_str,
                    'MEINS': meins_str,
                    'WERKS': werks_str,
                    'MAKTX': maktx,
                    'DMBTR': dmbtr_str,
                    'WAERS': waers,
                    'LIFNR': row.get('LIFNR', '')
                }
            )
            created_activities.append(activity)
            raw_record.processed_status = 'PROCESSED'
            raw_record.save()
            success_cnt += 1

        except Exception as e:
            raw_record.processed_status = 'ERROR'
            raw_record.error_message = str(e)
            raw_record.save()
            error_cnt += 1
            status = 'ERROR'
            # Create dummy error activity to show in the analyst review table! Very helpful.
            NormalizedActivity.objects.create(
                tenant=tenant,
                ingestion_job=job,
                raw_record=raw_record,
                scope='Scope 1',
                category='SAP Error Row',
                quantity=Decimal('0'),
                unit='-',
                co2e_kg=Decimal('0'),
                start_date=date.today(),
                end_date=date.today(),
                status='ERROR',
                validation_issues=[f"Ingestion failed: {str(e)}"],
                original_data=row
            )

    job.row_count = row_idx
    job.success_count = success_cnt
    job.error_count = error_cnt
    if error_cnt > 0:
        job.status = 'PARTIAL' if success_cnt > 0 else 'FAILED'
    job.save()

    return job, created_activities


def parse_utility_csv(tenant, csv_content, file_name):
    """
    Parses PG&E style Utility Portal Exports.
    CSV columns:
    Account_Number, Meter_Number, Billing_Start_Date, Billing_End_Date, Usage_kWh, Tariff_Name, Demand_kW, Total_Charges_USD, Read_Status
    Handles linear calendar month interpolation.
    """
    job = IngestionJob.objects.create(
        tenant=tenant,
        source_type='UTILITY',
        file_name=file_name,
        status='SUCCESS'
    )
    
    reader = csv.DictReader(io.StringIO(csv_content))
    reader.fieldnames = [name.strip() if name else "" for name in reader.fieldnames]
    
    required_fields = ['Account_Number', 'Meter_Number', 'Billing_Start_Date', 'Billing_End_Date', 'Usage_kWh']
    missing_headers = [f for f in required_fields if f not in reader.fieldnames]
    if missing_headers:
        job.status = 'FAILED'
        job.notes = f"Missing utility headers: {', '.join(missing_headers)}"
        job.save()
        return job, []

    created_activities = []
    row_idx = 0
    success_cnt = 0
    error_cnt = 0

    plants = {p.plant_code.upper(): p for p in tenant.plants.all()}
    
    # We will track active billing period intervals per meter to check for overlaps
    # meter_id -> list of (start_date, end_date)
    existing_periods = {}

    for row in reader:
        row_idx += 1
        raw_record = RawSourceRecord.objects.create(
            ingestion_job=job,
            tenant=tenant,
            row_index=row_idx,
            raw_data=row
        )
        
        try:
            acct_no = row.get('Account_Number')
            meter_no = row.get('Meter_Number', '').strip().upper()
            start_str = row.get('Billing_Start_Date')
            end_str = row.get('Billing_End_Date')
            usage_str = row.get('Usage_kWh')
            tariff = row.get('Tariff_Name', '')
            demand_str = row.get('Demand_kW', '0')
            charges_str = row.get('Total_Charges_USD', '0')
            read_status = row.get('Read_Status', 'Actual')

            # Parse dates
            start_date = parse_date(start_str)
            end_date = parse_date(end_str)

            if start_date >= end_date:
                raise ValueError(f"Start date ({start_str}) must be before end date ({end_str})")

            # Parse usage
            try:
                total_usage = Decimal(usage_str)
            except Exception:
                raise ValueError(f"Invalid Usage_kWh consumption: {usage_str}")

            try:
                total_charges = Decimal(charges_str)
            except Exception:
                total_charges = Decimal('0')

            issues = []
            status = 'PENDING'

            # Overlap billing check
            if meter_no not in existing_periods:
                existing_periods[meter_no] = []
            
            overlap_detected = False
            for s, e in existing_periods[meter_no]:
                if max(start_date, s) <= min(end_date, e):
                    overlap_detected = True
                    break
            
            if overlap_detected:
                issues.append("Billing period overlap detected with another record for this meter.")
                status = 'FLAGGED'
            
            existing_periods[meter_no].append((start_date, end_date))

            # Grid emission factor lookup based on meter plant mapping
            # Plant is looked up by meter number (or fall back to tenant's first plant)
            plant_obj = plants.get(meter_no)
            if not plant_obj:
                # Try finding a plant with matching name or use default
                plant_obj = tenant.plants.first()
                if plant_obj:
                    issues.append(f"Meter '{meter_no}' not explicitly mapped to a plant. Used default Plant: {plant_obj.plant_code}")
                else:
                    issues.append("No active plants defined for tenant. Used national grid fallback factor.")
            
            grid_factor = Decimal('0.385') # Fallback (US National Grid average)
            if plant_obj:
                grid_factor = plant_obj.grid_emission_factor

            # Perform calendar month linear interpolation
            sub_periods, total_days = get_days_per_month(start_date, end_date)
            
            # If the billing cycle spans multiple months, split it proportionally
            is_split = len(sub_periods) > 1
            if is_split:
                issues.append(f"Billing period of {total_days} days split across {len(sub_periods)} calendar months.")

            for sub in sub_periods:
                # Pro-rate consumption and charges
                days = sub['days']
                pro_rated_usage = (total_usage * Decimal(days)) / Decimal(total_days)
                pro_rated_charges = (total_charges * Decimal(days)) / Decimal(total_days)
                
                # Compute emissions
                co2e = pro_rated_usage * grid_factor
                
                sub_issues = list(issues)
                sub_status = status

                if pro_rated_usage < 0:
                    sub_issues.append("Negative billing usage value.")
                    sub_status = 'FLAGGED'

                # Spike Check: Usage spike > 30,000 kWh per month
                if pro_rated_usage > 30000:
                    sub_issues.append("Excessive electricity consumption warning (>30,000 kWh/mo).")
                    sub_status = 'FLAGGED'

                activity = NormalizedActivity.objects.create(
                    tenant=tenant,
                    ingestion_job=job,
                    raw_record=raw_record,
                    scope='Scope 2',
                    category='Electricity - Grid',
                    quantity=pro_rated_usage,
                    unit='kWh',
                    co2e_kg=co2e,
                    start_date=sub['start'],
                    end_date=sub['end'],
                    plant_code=plant_obj.plant_code if plant_obj else 'GRID-FALLBACK',
                    status=sub_status,
                    validation_issues=sub_issues,
                    original_data={
                        'Account_Number': acct_no,
                        'Meter_Number': meter_no,
                        'Billing_Start_Date': start_str,
                        'Billing_End_Date': end_str,
                        'Usage_kWh': usage_str,
                        'Tariff_Name': tariff,
                        'Demand_kW': demand_str,
                        'Total_Charges_USD': charges_str,
                        'Read_Status': read_status,
                        'Pro_Rated_Days': days,
                        'Total_Billing_Days': total_days
                    }
                )
                created_activities.append(activity)

            raw_record.processed_status = 'PROCESSED'
            raw_record.save()
            success_cnt += 1

        except Exception as e:
            raw_record.processed_status = 'ERROR'
            raw_record.error_message = str(e)
            raw_record.save()
            error_cnt += 1
            
            NormalizedActivity.objects.create(
                tenant=tenant,
                ingestion_job=job,
                raw_record=raw_record,
                scope='Scope 2',
                category='Utility Error Row',
                quantity=Decimal('0'),
                unit='-',
                co2e_kg=Decimal('0'),
                start_date=date.today(),
                end_date=date.today(),
                status='ERROR',
                validation_issues=[f"Ingestion failed: {str(e)}"],
                original_data=row
            )

    job.row_count = row_idx
    job.success_count = success_cnt
    job.error_count = error_cnt
    if error_cnt > 0:
        job.status = 'PARTIAL' if success_cnt > 0 else 'FAILED'
    job.save()

    return job, created_activities


def parse_travel_csv(tenant, csv_content, file_name):
    """
    Parses travel system CSV exports (from platforms like Concur or Navan).
    CSV headers:
    Booking_ID, Passenger_Name, Passenger_Email, Trip_Start_Date, Trip_End_Date, Category, Origin, Destination, Cabin_Class, Distance_km, Nights, Spend_Amount, Spend_Currency
    """
    job = IngestionJob.objects.create(
        tenant=tenant,
        source_type='TRAVEL',
        file_name=file_name,
        status='SUCCESS'
    )
    
    reader = csv.DictReader(io.StringIO(csv_content))
    reader.fieldnames = [name.strip() if name else "" for name in reader.fieldnames]
    
    required_fields = ['Booking_ID', 'Category', 'Trip_Start_Date']
    missing_headers = [f for f in required_fields if f not in reader.fieldnames]
    if missing_headers:
        job.status = 'FAILED'
        job.notes = f"Missing travel headers: {', '.join(missing_headers)}"
        job.save()
        return job, []

    created_activities = []
    row_idx = 0
    success_cnt = 0
    error_cnt = 0

    # Prefetch Lookups
    efs = {ef.category.lower(): ef for ef in EmissionFactor.objects.all()}
    airports = {a.iata_code.upper(): a for a in AirportLookup.objects.all()}

    for row in reader:
        row_idx += 1
        raw_record = RawSourceRecord.objects.create(
            ingestion_job=job,
            tenant=tenant,
            row_index=row_idx,
            raw_data=row
        )
        
        try:
            booking_id = row.get('Booking_ID')
            p_name = row.get('Passenger_Name', '')
            p_email = row.get('Passenger_Email', '')
            start_str = row.get('Trip_Start_Date')
            end_str = row.get('Trip_End_Date', start_str)
            category_str = row.get('Category', '').strip().capitalize() # Flight, Hotel, Ground
            origin_str = row.get('Origin', '').strip().upper()
            dest_str = row.get('Destination', '').strip().upper()
            cabin_str = row.get('Cabin_Class', '').strip().capitalize() # Economy, Business, First
            dist_str = row.get('Distance_km', '0')
            nights_str = row.get('Nights', '0')
            spend_str = row.get('Spend_Amount', '0')
            currency = row.get('Spend_Currency', 'USD')

            start_date = parse_date(start_str)
            end_date = parse_date(end_str)

            issues = []
            status = 'PENDING'

            # Anomaly: Date in Future
            if start_date > date.today():
                issues.append("Trip occurs in the future.")
                status = 'FLAGGED'

            # Ingestion logic depending on travel category
            scope = 'Scope 3'
            norm_category = 'Business Travel'
            quantity = Decimal('0')
            unit = ''
            co2e = Decimal('0')

            if category_str == 'Flight':
                norm_category = 'Flight - Economy'
                unit = 'p-km' # Passenger-Kilometers
                
                # Parse or compute distance
                distance = Decimal('0')
                try:
                    distance = Decimal(dist_str)
                except Exception:
                    distance = Decimal('0')

                # If distance isn't given, compute via airport codes lookup
                if distance <= 0:
                    if origin_str and dest_str:
                        orig_ap = airports.get(origin_str)
                        dest_ap = airports.get(dest_str)
                        
                        if orig_ap and dest_ap:
                            computed_dist = haversine_distance(
                                orig_ap.latitude, orig_ap.longitude,
                                dest_ap.latitude, dest_ap.longitude
                            )
                            distance = Decimal(str(computed_dist))
                            issues.append(f"Computed flight distance ({distance} km) dynamically using IATA airport coordinates ({origin_str} -> {dest_str}).")
                        else:
                            missing_aps = []
                            if not orig_ap: missing_aps.append(origin_str)
                            if not dest_ap: missing_aps.append(dest_str)
                            
                            distance = Decimal('1200') # default segment fallback
                            issues.append(f"Airport coordinates not found for {', '.join(missing_aps)}. Used default flight segment distance: 1200 km.")
                            status = 'FLAGGED'
                    else:
                        distance = Decimal('1200')
                        issues.append("Missing flight airport routing. Used fallback segment distance: 1200 km.")
                        status = 'FLAGGED'

                quantity = distance
                
                # Check cabin class
                ef_key = 'flight - economy'
                if cabin_str == 'Business':
                    norm_category = 'Flight - Business'
                    ef_key = 'flight - business'
                elif cabin_str == 'First':
                    norm_category = 'Flight - First'
                    ef_key = 'flight - first'
                elif cabin_str and cabin_str != 'Economy':
                    issues.append(f"Unknown cabin class '{cabin_str}'. Defaulted to Economy factors.")

                # CO2e calculation
                factor_obj = efs.get(ef_key)
                if factor_obj:
                    co2e = quantity * factor_obj.factor
                else:
                    fallback_factor = Decimal('0.14') # Default kgCO2e/km Economy
                    if cabin_str == 'Business': fallback_factor = Decimal('0.25')
                    elif cabin_str == 'First': fallback_factor = Decimal('0.38')
                    co2e = quantity * fallback_factor
                    issues.append(f"Cabin factor for {cabin_str} not in database. Used fallback: {fallback_factor} kgCO2e/km.")

            elif category_str == 'Hotel':
                norm_category = 'Hotel - Stay'
                unit = 'room-night'
                
                try:
                    nights = int(nights_str)
                except ValueError:
                    nights = 0

                if nights <= 0:
                    # Calculate nights based on start and end date
                    nights = (end_date - start_date).days
                    if nights <= 0:
                        nights = 1
                    issues.append(f"Missing hotel room nights. Inferred {nights} nights from booking dates.")

                quantity = Decimal(str(nights))
                
                # CO2e calculation
                factor_obj = efs.get('hotel - stay')
                if factor_obj:
                    co2e = quantity * factor_obj.factor
                else:
                    factor_val = Decimal('18.4') # kgCO2e/night fallback
                    co2e = quantity * factor_val
                    issues.append(f"Hotel emission factor not found. Used standard fallback: {factor_val} kgCO2e/night.")

            elif category_str in ('Ground', 'Taxi', 'Train', 'Car'):
                # Handle ground travel
                norm_category = 'Ground - Taxi'
                unit = 'km'
                
                # Parse distance
                distance = Decimal('0')
                try:
                    distance = Decimal(dist_str)
                except ValueError:
                    distance = Decimal('0')

                # Fallback: estimate ground distance based on travel spend
                if distance <= 0:
                    try:
                        spend = Decimal(spend_str)
                        distance = spend * Decimal('1.5') # Assume 1.5 km per USD spend
                        issues.append(f"Ground distance missing. Estimated distance of {distance:.1f} km from spend (${spend}).")
                    except ValueError:
                        distance = Decimal('15') # flat fallback
                        issues.append("Missing ground distance. Defaulted to fallback: 15 km.")

                quantity = distance

                ef_key = 'ground - taxi'
                if category_str == 'Train':
                    norm_category = 'Ground - Train'
                    ef_key = 'ground - train'
                elif category_str == 'Car':
                    norm_category = 'Ground - Rental Car'
                    ef_key = 'ground - rental car'

                factor_obj = efs.get(ef_key)
                if factor_obj:
                    co2e = quantity * factor_obj.factor
                else:
                    # Generic ground factor fallback (0.18 kgCO2e/km)
                    factor_val = Decimal('0.18')
                    if category_str == 'Train': factor_val = Decimal('0.04')
                    co2e = quantity * factor_val
                    issues.append(f"Ground factor for '{category_str}' not found. Used fallback: {factor_val} kgCO2e/km.")

            else:
                raise ValueError(f"Unsupported travel category: '{category_str}'")

            # Travel Anomaly Check (extreme mileage or hotel stay)
            if quantity <= 0:
                issues.append("Activity quantity is zero or negative.")
                status = 'FLAGGED'

            if category_str == 'Flight' and quantity > 15000:
                issues.append("Extreme flight distance (>15,000 km) flagged for review.")
                status = 'FLAGGED'

            activity = NormalizedActivity.objects.create(
                tenant=tenant,
                ingestion_job=job,
                raw_record=raw_record,
                scope=scope,
                category=norm_category,
                quantity=quantity,
                unit=unit,
                co2e_kg=co2e,
                start_date=start_date,
                end_date=end_date,
                origin_airport=origin_str if category_str == 'Flight' else None,
                destination_airport=dest_str if category_str == 'Flight' else None,
                cabin_class=cabin_str if category_str == 'Flight' else None,
                hotel_nights=nights if category_str == 'Hotel' else None,
                status=status,
                validation_issues=issues,
                original_data={
                    'Booking_ID': booking_id,
                    'Passenger_Name': p_name,
                    'Passenger_Email': p_email,
                    'Trip_Start_Date': start_str,
                    'Trip_End_Date': end_str,
                    'Category': category_str,
                    'Origin': origin_str,
                    'Destination': dest_str,
                    'Cabin_Class': cabin_str,
                    'Distance_km': dist_str,
                    'Nights': nights_str,
                    'Spend_Amount': spend_str,
                    'Spend_Currency': currency
                }
            )
            created_activities.append(activity)
            raw_record.processed_status = 'PROCESSED'
            raw_record.save()
            success_cnt += 1

        except Exception as e:
            raw_record.processed_status = 'ERROR'
            raw_record.error_message = str(e)
            raw_record.save()
            error_cnt += 1
            
            NormalizedActivity.objects.create(
                tenant=tenant,
                ingestion_job=job,
                raw_record=raw_record,
                scope='Scope 3',
                category='Travel Error Row',
                quantity=Decimal('0'),
                unit='-',
                co2e_kg=Decimal('0'),
                start_date=date.today(),
                end_date=date.today(),
                status='ERROR',
                validation_issues=[f"Ingestion failed: {str(e)}"],
                original_data=row
            )

    job.row_count = row_idx
    job.success_count = success_cnt
    job.error_count = error_cnt
    if error_cnt > 0:
        job.status = 'PARTIAL' if success_cnt > 0 else 'FAILED'
    job.save()

    return job, created_activities
