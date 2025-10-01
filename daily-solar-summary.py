#!/usr/bin/env python3
"""
Daily Solar Summary Script (runs once per day in early morning)
Reads previous day's data from CSV files
calculates daily totals,
Saves new daily stats to local file
Writes to Google Sheets if the credentials exist in config.py
Checks for underperforming inverters, and alers
Emails monthly summary to admin email defined in config.py
"""

import csv
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Import config
try:
    from config import GOOGLE_API_CREDENTIALS, GOOGLE_SHEET_SPREADSHEET_ID
    GOOGLE_SHEETS_ENABLED = True
except (ImportError, AttributeError):
    print("Note: Google Sheets credentials not configured, will save to local CSV only")
    GOOGLE_SHEETS_ENABLED = False
    GOOGLE_API_CREDENTIALS = None
    GOOGLE_SHEET_SPREADSHEET_ID = None

# Configuration
OUTPUT_DIR = Path('PVS6_output')
OVERVIEW_CSV = OUTPUT_DIR / 'PVS6_output_overview.csv'
INVERTERS_CSV = OUTPUT_DIR / 'PVS6_output_inverters.csv'
DAILY_SUMMARY_CSV = OUTPUT_DIR / 'daily_summary.csv'
SHEET_NAME = 'DailySolarSummary'
UNDERPERFORMANCE_THRESHOLD = 0.80  # Alert if inverter produces <80% of average

class DailySolarSummary:
    def __init__(self):
        # Setup Google Sheets only if credentials available
        self.sheets_enabled = GOOGLE_SHEETS_ENABLED
        
        if self.sheets_enabled:
            try:
                creds = service_account.Credentials.from_service_account_info(
                    GOOGLE_API_CREDENTIALS,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                self.service = build('sheets', 'v4', credentials=creds)
                self.sheet = self.service.spreadsheets()
                print("✅ Google Sheets API connected")
            except Exception as e:
                print(f"⚠️  Error setting up Google Sheets: {e}")
                print("Will save to local CSV only")
                self.sheets_enabled = False
                self.service = None
                self.sheet = None
        else:
            self.service = None
            self.sheet = None
    
    def get_date_range(self, days_ago):
        """Get start and end datetime for a specific day"""
        target_date = datetime.now().date() - timedelta(days=days_ago)
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
        return start, end, target_date
    
    def read_overview_for_date(self, target_date):
        """Read overview CSV and get first and last entries for a specific date"""
        if not OVERVIEW_CSV.exists():
            print(f"Error: {OVERVIEW_CSV} not found")
            return None, None
        
        first_entry = None
        last_entry = None
        
        with open(OVERVIEW_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S')
                if timestamp.date() == target_date:
                    if first_entry is None:
                        first_entry = row
                    last_entry = row
        
        return first_entry, last_entry
    
    def read_inverters_for_date(self, target_date):
        """Read inverter CSV and get first and last entries per inverter for a specific date"""
        if not INVERTERS_CSV.exists():
            print(f"Error: {INVERTERS_CSV} not found")
            return {}
        
        inverter_data = defaultdict(lambda: {'first': None, 'last': None})
        
        with open(INVERTERS_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S')
                if timestamp.date() == target_date:
                    serial = row['Serial Number']
                    if inverter_data[serial]['first'] is None:
                        inverter_data[serial]['first'] = row
                    inverter_data[serial]['last'] = row
        
        return dict(inverter_data)
    
    def calculate_daily_totals(self, first_overview, last_overview):
        """Calculate daily production, consumption, and net from lifetime values"""
        if not first_overview or not last_overview:
            return None
        
        daily_pv = float(last_overview['Lifetime PV Production (kWh)']) - float(first_overview['Lifetime PV Production (kWh)'])
        daily_load = float(last_overview['Lifetime Site Load (kWh)']) - float(first_overview['Lifetime Site Load (kWh)'])
        daily_net = float(last_overview['Lifetime Net (kWh)']) - float(first_overview['Lifetime Net (kWh)'])
        
        return {
            'daily_pv_kwh': daily_pv,
            'daily_load_kwh': daily_load,
            'daily_net_kwh': daily_net,
            'lifetime_pv_kwh': float(last_overview['Lifetime PV Production (kWh)']),
            'lifetime_load_kwh': float(last_overview['Lifetime Site Load (kWh)']),
            'lifetime_net_kwh': float(last_overview['Lifetime Net (kWh)'])
        }
    
    def calculate_inverter_daily_production(self, inverter_data):
        """Calculate daily production for each inverter"""
        daily_production = {}
        
        for serial, data in inverter_data.items():
            if data['first'] and data['last']:
                first_kwh = float(data['first']['Lifetime Energy (kWh)'])
                last_kwh = float(data['last']['Lifetime Energy (kWh)'])
                daily_production[serial] = last_kwh - first_kwh
        
        return daily_production
    
    def check_underperforming_inverters(self, daily_production):
        """Identify inverters producing significantly less than average"""
        if not daily_production:
            return []
        
        # Calculate average production
        values = list(daily_production.values())
        avg_production = sum(values) / len(values)
        
        # Find underperformers
        underperformers = []
        for serial, production in daily_production.items():
            if production < (avg_production * UNDERPERFORMANCE_THRESHOLD):
                percentage = (production / avg_production * 100) if avg_production > 0 else 0
                underperformers.append({
                    'serial': serial,
                    'production': production,
                    'average': avg_production,
                    'percentage': percentage
                })
        
        return underperformers
    
    def write_to_google_sheets(self, date, daily_totals, daily_production, underperformers):
        """Write daily summary to Google Sheets"""
        if not self.sheets_enabled or not self.sheet:
            print("Google Sheets not available, skipping")
            return
        
        date_str = date.strftime('%Y-%m-%d')
        
        # Build alert text
        alert_text = ""
        if underperformers:
            alert_parts = [f"{u['serial']} ({u['percentage']:.0f}%)" for u in underperformers]
            alert_text = "⚠️ " + ", ".join(alert_parts)
        
        row = [
            date_str,
            daily_totals['daily_pv_kwh'],
            daily_totals['daily_load_kwh'],
            daily_totals['daily_net_kwh'],
            daily_totals['lifetime_pv_kwh'],
            daily_totals['lifetime_load_kwh'],
            daily_totals['lifetime_net_kwh'],
            len(daily_production),
            alert_text
        ]
        
        try:
            # Check if headers exist
            result = self.sheet.values().get(
                spreadsheetId=GOOGLE_SHEET_SPREADSHEET_ID,
                range=f'{SHEET_NAME}!A1:I1'
            ).execute()
            
            if not result.get('values'):
                # Write headers
                headers = [[
                    'Date',
                    'Daily PV Production (kWh)',
                    'Daily Site Load (kWh)',
                    'Daily Net Grid (kWh)',
                    'Lifetime PV (kWh)',
                    'Lifetime Load (kWh)',
                    'Lifetime Net (kWh)',
                    'Inverters Reporting',
                    'Alerts'
                ]]
                self.sheet.values().update(
                    spreadsheetId=GOOGLE_SHEET_SPREADSHEET_ID,
                    range=f'{SHEET_NAME}!A1:I1',
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                print("✅ Created headers in Google Sheets")
            
            # Append data row
            result = self.sheet.values().append(
                spreadsheetId=GOOGLE_SHEET_SPREADSHEET_ID,
                range=f'{SHEET_NAME}!A:I',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            print(f"✅ Written to Google Sheets: {date_str}")
            
        except Exception as e:
            print(f"❌ Error writing to Google Sheets: {e}")
    
    def date_exists_in_csv(self, date):
        """Check if date already exists in local CSV"""
        if not DAILY_SUMMARY_CSV.exists():
            return False
        
        date_str = date.strftime('%Y-%m-%d')
        
        try:
            with open(DAILY_SUMMARY_CSV, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['Date'] == date_str:
                        return True
        except Exception:
            pass
        
        return False
    
    def write_to_local_csv(self, date, daily_totals, daily_production, underperformers):
        """Write daily summary to local CSV - returns True if written, False if skipped"""
        date_str = date.strftime('%Y-%m-%d')
        
        # Check if date already exists
        if self.date_exists_in_csv(date):
            print(f"⚠️  Date {date_str} already exists in {DAILY_SUMMARY_CSV}, skipping")
            return False
        
        # Build alert text
        alert_text = ""
        if underperformers:
            alert_parts = [f"{u['serial']} ({u['percentage']:.0f}%)" for u in underperformers]
            alert_text = "⚠️ " + ", ".join(alert_parts)
        
        # Check if file exists to determine if we need headers
        file_exists = DAILY_SUMMARY_CSV.exists()
        
        try:
            with open(DAILY_SUMMARY_CSV, 'a', newline='') as f:
                writer = csv.writer(f)
                
                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        'Date',
                        'Daily PV Production (kWh)',
                        'Daily Site Load (kWh)',
                        'Daily Net Grid (kWh)',
                        'Lifetime PV (kWh)',
                        'Lifetime Load (kWh)',
                        'Lifetime Net (kWh)',
                        'Inverters Reporting',
                        'Alerts'
                    ])
                
                # Write data row
                writer.writerow([
                    date_str,
                    daily_totals['daily_pv_kwh'],
                    daily_totals['daily_load_kwh'],
                    daily_totals['daily_net_kwh'],
                    daily_totals['lifetime_pv_kwh'],
                    daily_totals['lifetime_load_kwh'],
                    daily_totals['lifetime_net_kwh'],
                    len(daily_production),
                    alert_text
                ])
            
            print(f"✅ Appended to local CSV: {DAILY_SUMMARY_CSV}")
            return True
            
        except Exception as e:
            print(f"❌ Error writing to local CSV: {e}")
            return False
    
    def run(self, days_ago=1):
        """Run daily summary for specified day (default: yesterday)"""
        print(f"Daily Solar Summary - Processing {days_ago} day(s) ago")
        print("="*60)
        
        # Get target date
        start, end, target_date = self.get_date_range(days_ago)
        print(f"Target date: {target_date}")
        
        # Read data from CSVs
        print("\nReading overview data...")
        first_overview, last_overview = self.read_overview_for_date(target_date)
        
        if not first_overview or not last_overview:
            print(f"❌ No overview data found for {target_date}")
            return
        
        print(f"Found {first_overview['Timestamp']} to {last_overview['Timestamp']}")
        
        print("\nReading inverter data...")
        inverter_data = self.read_inverters_for_date(target_date)
        print(f"Found data for {len(inverter_data)} inverters")
        
        # Calculate daily totals
        print("\nCalculating daily totals...")
        daily_totals = self.calculate_daily_totals(first_overview, last_overview)
        
        if daily_totals:
            print(f"  Daily PV Production: {daily_totals['daily_pv_kwh']:.2f} kWh")
            print(f"  Daily Site Load: {daily_totals['daily_load_kwh']:.2f} kWh")
            print(f"  Daily Net Grid: {daily_totals['daily_net_kwh']:.2f} kWh")
        
        # Calculate inverter daily production
        print("\nCalculating per-inverter production...")
        daily_production = self.calculate_inverter_daily_production(inverter_data)
        
        for serial, production in daily_production.items():
            print(f"  {serial}: {production:.2f} kWh")
        
        # Check for underperformers
        print("\nChecking for underperforming inverters...")
        underperformers = self.check_underperforming_inverters(daily_production)
        
        if underperformers:
            print("⚠️  ALERT: Underperforming inverters detected!")
            for u in underperformers:
                print(f"  {u['serial']}: {u['production']:.2f} kWh ({u['percentage']:.0f}% of avg {u['average']:.2f} kWh)")
        else:
            print("✅ All inverters performing within expected range")
        
        # Write to local CSV
        print("\nWriting to local CSV...")
        written = self.write_to_local_csv(target_date, daily_totals, daily_production, underperformers)
        
        # Write to Google Sheets only if local CSV was written
        if written and self.sheets_enabled:
            print("\nWriting to Google Sheets...")
            self.write_to_google_sheets(target_date, daily_totals, daily_production, underperformers)
        elif not written:
            print("\nSkipping Google Sheets (duplicate date)")
        
        print("\n✅ Daily summary completed!")

if __name__ == '__main__':
    summary = DailySolarSummary()
    
    # Check if testing mode (can specify days ago)
    if len(sys.argv) > 1:
        try:
            days_ago = int(sys.argv[1])
            summary.run(days_ago=days_ago)
        except ValueError:
            print("Usage: python daily-solar-summary.py [days_ago]")
            sys.exit(1)
    else:
        summary.run(days_ago=1)  # Default: yesterday