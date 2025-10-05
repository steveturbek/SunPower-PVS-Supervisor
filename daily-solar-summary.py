#!/usr/bin/env python3
"""
Daily Solar Summary Script (runs once per day in early morning)
Reads previous day's data from CSV files
calculates daily totals,
Saves new daily stats to local file
Writes to Google Sheets if the credentials exist in config.py
Checks for underperforming inverters, and alerts
Emails monthly summary to admin email defined in config.py
"""

import csv
import sys
import smtplib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Import config
try:
    from config import GOOGLE_API_CREDENTIALS, GOOGLE_SHEET_SPREADSHEET_ID, GOOGLE_SHEET_TAB_NAME
    GOOGLE_SHEETS_ENABLED = True
except (ImportError, AttributeError):
    print("Note: Google Sheets credentials not configured, will save to local CSV only")
    GOOGLE_SHEETS_ENABLED = False
    GOOGLE_API_CREDENTIALS = None
    GOOGLE_SHEET_SPREADSHEET_ID = None
    GOOGLE_SHEET_TAB_NAME = None

# Import email config
try:
    from config import (
        SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
        EMAIL_FROM, SUPERVISOR_EMAIL
    )
    # Check if any critical email variables are None or empty
    if all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, SUPERVISOR_EMAIL]):
        EMAIL_ENABLED = True
        print("\t✓ Email alerts enabled")
    else:
        EMAIL_ENABLED = False
        print("\tNote: Email credentials incomplete, will skip email alerts")
except (ImportError, AttributeError):
    print("\tNote: Email credentials not configured, will skip email alerts")
    EMAIL_ENABLED = False
    SMTP_SERVER = SMTP_PORT = SMTP_USERNAME = SMTP_PASSWORD = None
    EMAIL_FROM = SUPERVISOR_EMAIL = None

# Import file paths from config
try:
    from config import OUTPUT_DIR, OVERVIEW_CSV, INVERTERS_CSV, DAILY_SUMMARY_CSV
except (ImportError, AttributeError):
    # Fallback to defaults if not in config
    OUTPUT_DIR = Path('output')
    OVERVIEW_CSV = OUTPUT_DIR / 'overview.csv'
    INVERTERS_CSV = OUTPUT_DIR / 'inverters.csv'
    DAILY_SUMMARY_CSV = OUTPUT_DIR / 'daily_summary.csv'



try:
    from config import UNDERPERFORMANCE_THRESHOLD
except (ImportError, AttributeError):
    UNDERPERFORMANCE_THRESHOLD = 0.80  # Default fallback

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
                print("\t✓ Google Sheets API connected")
            except Exception as e:
                print(f"⚠️  Error setting up Google Sheets: {e}")
                print("\tWill save to local CSV only")
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
                    # Skip test data (serial numbers with repeating patterns like E00123456789)
                    if serial == 'E00123456789':
                        continue
                    if inverter_data[serial]['first'] is None:
                        inverter_data[serial]['first'] = row
                    inverter_data[serial]['last'] = row

        return dict(inverter_data)
    
    def calculate_daily_totals(self, first_overview, last_overview):
        """Calculate daily production, consumption, and net from lifetime values"""
        if not first_overview or not last_overview:
            return None
        
        daily_pv = float(last_overview['Lifetime PV Production (kWh)']) - float(first_overview['Lifetime PV Production (kWh)'])
        daily_consumption = float(last_overview['Lifetime Site Consumption (kWh)']) - float(first_overview['Lifetime Site Consumption (kWh)'])
        daily_net = float(last_overview['Lifetime Net (kWh)']) - float(first_overview['Lifetime Net (kWh)'])
        
        return {
            'daily_pv_kwh': daily_pv,
            'daily_consumption_kwh': daily_consumption,
            'daily_net_kwh': daily_net,
            'lifetime_pv_kwh': float(last_overview['Lifetime PV Production (kWh)']),
            'lifetime_consumption_kwh': float(last_overview['Lifetime Site Consumption (kWh)']),
            'lifetime_net_kwh': float(last_overview['Lifetime Net (kWh)'])
        }
    
    def calculate_inverter_daily_production(self, inverter_data):
        """Calculate daily production for each inverter"""
        daily_production = {}
        
        for serial, data in inverter_data.items():
            if data['first'] and data['last']:
                first_kwh = float(data['first']['Lifetime PV Production (kWh)'])
                last_kwh = float(data['last']['Lifetime PV Production (kWh)'])
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
    
    def send_email(self, subject, html_body, retry=True):
        """Send email alert - returns True if successful"""
        if not EMAIL_ENABLED:
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = SUPERVISOR_EMAIL
            
            # Attach HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
            
            print(f"✓ Email sent: {subject}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            
            # Retry once if requested
            if retry:
                print("\tRetrying email send...")
                return self.send_email(subject, html_body, retry=False)
            
            return False
    
    def send_underperformance_alert(self, date, underperformers, daily_production):
        """Send email alert for underperforming inverters"""
        subject = f"⚠️ Solar Alert: Underperforming Inverters - {date.strftime('%Y-%m-%d')}"
        
        # Calculate average
        avg_production = sum(daily_production.values()) / len(daily_production)
        
        # Build HTML email
        html = f"""
        <html>
        <body>
            <h2>Solar System Alert</h2>
            <p><strong>Date:</strong> {date.strftime('%Y-%m-%d')}</p>
            <p><strong>Issue:</strong> {len(underperformers)} inverter(s) producing significantly below average</p>
            
            <h3>Underperforming Inverters</h3>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th>Serial Number</th>
                    <th>Production (kWh)</th>
                    <th>% of Average</th>
                </tr>
        """
        
        for u in underperformers:
            html += f"""
                <tr>
                    <td>{u['serial']}</td>
                    <td>{u['production']:.2f}</td>
                    <td style="color: red;"><strong>{u['percentage']:.0f}%</strong></td>
                </tr>
            """
        
        html += f"""
            </table>
            
            <h3>All Inverters (for comparison)</h3>
            <p><strong>Average production:</strong> {avg_production:.2f} kWh</p>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th>Serial Number</th>
                    <th>Production (kWh)</th>
                </tr>
        """
        
        for serial, production in sorted(daily_production.items(), key=lambda x: x[1], reverse=True):
            html += f"""
                <tr>
                    <td>{serial}</td>
                    <td>{production:.2f}</td>
                </tr>
            """
        
        html += """
            </table>
        </body>
        </html>
        """
        
        self.send_email(subject, html)
    
    def get_monthly_data(self, target_date):
        """Get all daily data for the month of target_date"""
        if not DAILY_SUMMARY_CSV.exists():
            return []
        
        month_data = []
        target_year = target_date.year
        target_month = target_date.month
        
        with open(DAILY_SUMMARY_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = datetime.strptime(row['Date'], '%Y-%m-%d').date()
                if date.year == target_year and date.month == target_month:
                    month_data.append(row)
        
        return month_data
    
    def get_previous_year_month_data(self, target_date):
        """Get same month from previous year for YOY comparison"""
        if not DAILY_SUMMARY_CSV.exists():
            return []
        
        prev_year = target_date.year - 1
        target_month = target_date.month
        
        month_data = []
        
        with open(DAILY_SUMMARY_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = datetime.strptime(row['Date'], '%Y-%m-%d').date()
                if date.year == prev_year and date.month == target_month:
                    month_data.append(row)
        
        return month_data
    
    def send_monthly_summary(self, target_date):
        """Send monthly summary email on first day of month"""
        
        # Get all monthly data from CSV to find all years with this month
        if not DAILY_SUMMARY_CSV.exists():
            print("\tNo monthly data available to send")
            return
        
        monthly_data_by_year = defaultdict(list)
        lifetime_pv = None
        
        with open(DAILY_SUMMARY_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = datetime.strptime(row['Date'], '%Y-%m-%d').date()
                if date.month == target_date.month:
                    monthly_data_by_year[date.year].append(row)
                # Get most recent lifetime value
                if row.get('Lifetime PV (kWh)'):
                    lifetime_pv = float(row['Lifetime PV (kWh)'])
        
        if not monthly_data_by_year:
            print("\tNo monthly data available to send")
            return
        
        # Build lifetime info for subject line
        lifetime_str = f" | Lifetime: {lifetime_pv:.0f} kWh" if lifetime_pv else ""
        subject = f"☀️ Solar Monthly Summary - {target_date.strftime('%B %Y')}{lifetime_str}"
        
        # Build Year-over-Year comparison table with all years
        yoy_table = """
        <h3>Year-over-Year Comparison</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f0f0f0;">
                <th>Year</th>
                <th>Average Daily Production (kWh)</th>
                <th>Monthly PV Production (kWh)</th>
                <th>Monthly Site Consumption (kWh)</th>
                <th>Monthly Net Grid (kWh)</th>
            </tr>
        """
        
        # Sort years in descending order
        for year in sorted(monthly_data_by_year.keys(), reverse=True):
            year_data = monthly_data_by_year[year]
            
            # Calculate totals, handling empty values
            total_pv = sum(float(row['Daily PV Production (kWh)']) if row.get('Daily PV Production (kWh)') else 0.0 for row in year_data)
            total_consumption = sum(float(row['Daily Site Consumption (kWh)']) if row.get('Daily Site Consumption (kWh)') else 0.0 for row in year_data)
            total_net = sum(float(row['Daily Net Grid (kWh)']) if row.get('Daily Net Grid (kWh)') else 0.0 for row in year_data)
            days_reporting = len(year_data)
            avg_daily = (total_pv / days_reporting) if days_reporting > 0 else 0
            
            # Format values, show ? for zero values
            avg_daily_str = f"{avg_daily:.1f}" if avg_daily > 0 else "?"
            total_pv_str = f"{total_pv:.1f}" if total_pv > 0 else "?"
            total_consumption_str = f"{total_consumption:.1f}" if total_consumption > 0 else "?"
            total_net_str = f"{total_net:.1f}" if total_net > 0 else "?"
            
            yoy_table += f"""
            <tr>
                <td><strong>{year}</strong></td>
                <td>{avg_daily_str}</td>
                <td>{total_pv_str}</td>
                <td>{total_consumption_str}</td>
                <td>{total_net_str}</td>
            </tr>
            """
        
        yoy_table += "</table>"
        
        # Get current month data for daily breakdown
        current_year = max(monthly_data_by_year.keys())
        month_data = monthly_data_by_year[current_year]
        
        # Build daily data table
        daily_table = """
        <h3>Daily Breakdown</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f0f0f0;">
                <th>Date</th>
                <th>PV Production (kWh)</th>
                <th>Site Consumption (kWh)</th>
                <th>Net Grid (kWh)</th>
                <th>Alerts</th>
            </tr>
        """
        
        for row in month_data:
            alert_cell = row.get('Alerts', '')
            alert_style = ' style="background-color: #fff3cd;"' if alert_cell else ''
            
            # Handle empty values
            pv_val = float(row['Daily PV Production (kWh)']) if row.get('Daily PV Production (kWh)') else 0.0
            consumption_val = float(row['Daily Site Consumption (kWh)']) if row.get('Daily Site Consumption (kWh)') else 0.0
            net_val = float(row['Daily Net Grid (kWh)']) if row.get('Daily Net Grid (kWh)') else 0.0
            
            daily_table += f"""
            <tr{alert_style}>
                <td>{row['Date']}</td>
                <td>{pv_val:.1f}</td>
                <td>{consumption_val:.1f}</td>
                <td>{net_val:.1f}</td>
                <td>{alert_cell}</td>
            </tr>
            """
        
        daily_table += "</table>"
        
        # Build complete HTML email
        html = f"""
        <html>
        <body>
            <h2>Monthly Solar Summary - {target_date.strftime('%B %Y')}</h2>
            
            {yoy_table}
            
            {daily_table}
            
            <p style="margin-top: 20px; color: #666; font-size: 0.9em;">
                This is an automated monthly summary from your solar monitoring system.
            </p>
        </body>
        </html>
        """
        
        self.send_email(subject, html)
    
    def write_to_google_sheets(self, date, daily_totals, daily_production, underperformers):
        """Write daily summary to Google Sheets"""
        if not self.sheets_enabled or not self.sheet:
            print("\tGoogle Sheets not available, skipping")
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
            daily_totals['daily_consumption_kwh'],
            daily_totals['daily_net_kwh'],
            daily_totals['lifetime_pv_kwh'],
            daily_totals['lifetime_consumption_kwh'],
            daily_totals['lifetime_net_kwh'],
            len(daily_production),
            alert_text
        ]
        
        try:
            # Check if headers exist
            result = self.sheet.values().get(
                spreadsheetId=GOOGLE_SHEET_SPREADSHEET_ID,
                range=f'{GOOGLE_SHEET_TAB_NAME}!A1:I1'
            ).execute()
            
            if not result.get('values'):
                # Write headers
                headers = [[
                    'Date',
                    'Daily PV Production (kWh)',
                    'Daily Site Consumption (kWh)',
                    'Daily Net Grid (kWh)',
                    'Lifetime PV (kWh)',
                    'Lifetime Site Consumption (kWh)',
                    'Lifetime Net (kWh)',
                    'Inverters Reporting',
                    'Alerts'
                ]]
                self.sheet.values().update(
                    spreadsheetId=GOOGLE_SHEET_SPREADSHEET_ID,
                    range=f'{GOOGLE_SHEET_TAB_NAME}!A1:I1',
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                print("\t✓ Created headers in Google Sheets")
            
            # Append data row
            result = self.sheet.values().append(
                spreadsheetId=GOOGLE_SHEET_SPREADSHEET_ID,
                range=f'{GOOGLE_SHEET_TAB_NAME}!A:I',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            print(f"✓ Written to Google Sheets: {date_str}")
            
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
                        'Daily Site Consumption (kWh)',
                        'Daily Net Grid (kWh)',
                        'Lifetime PV (kWh)',
                        'Lifetime Site Consumption (kWh)',
                        'Lifetime Net (kWh)',
                        'Inverters Reporting',
                        'Alerts'
                    ])
                
                # Write data row
                writer.writerow([
                    date_str,
                    round(daily_totals['daily_pv_kwh'], 1),
                    round(daily_totals['daily_consumption_kwh'], 1),
                    round(daily_totals['daily_net_kwh'], 1),
                    daily_totals['lifetime_pv_kwh'],
                    daily_totals['lifetime_consumption_kwh'],
                    daily_totals['lifetime_net_kwh'],
                    len(daily_production),
                    alert_text
                ])
            
            print(f"✓ Appended to local CSV: {DAILY_SUMMARY_CSV}")
            return True
            
        except Exception as e:
            print(f"❌ Error writing to local CSV: {e}")
            return False
    
    def run(self, days_ago=1):
        """Run daily summary for specified day (default: yesterday)"""
        print(f"\tDaily Solar Summary - Processing {days_ago} day(s) ago")
        print("="*60)
        
        # Get target date
        start, end, target_date = self.get_date_range(days_ago)
        print(f"\tTarget date: {target_date}")
        
        # Read data from CSVs
        print("\n\tReading overview data...")
        first_overview, last_overview = self.read_overview_for_date(target_date)
        
        if not first_overview or not last_overview:
            print(f"\t❌ No overview data found for {target_date}")
            return
        
        print(f"\tFound {first_overview['Timestamp']} to {last_overview['Timestamp']}")
        
        print("\n\tReading inverter data...")
        inverter_data = self.read_inverters_for_date(target_date)
        print(f"\tFound data for {len(inverter_data)} inverters")
        
        # Calculate daily totals
        print("\n\rCalculating daily totals...")
        daily_totals = self.calculate_daily_totals(first_overview, last_overview)
        
        if daily_totals:
            print(f"\t  Daily PV Production: {daily_totals['daily_pv_kwh']:.2f} kWh")
            print(f"\t  Daily Site Consumption: {daily_totals['daily_consumption_kwh']:.2f} kWh")
            print(f"\t  Daily Net Grid: {daily_totals['daily_net_kwh']:.2f} kWh")
        
        # Calculate inverter daily production
        print("\n\tCalculating per-inverter production...")
        daily_production = self.calculate_inverter_daily_production(inverter_data)
        
        for serial, production in daily_production.items():
            print(f"  {serial}: {production:.2f} kWh")
        
        # Check for underperformers
        print("\n\tChecking for underperforming inverters...")
        underperformers = self.check_underperforming_inverters(daily_production)
        
        if underperformers:
            print("⚠️  ALERT: Underperforming inverters detected!")
            for u in underperformers:
                print(f"  {u['serial']}: {u['production']:.2f} kWh ({u['percentage']:.0f}% of avg {u['average']:.2f} kWh)")
            
            # Send email alert
            if EMAIL_ENABLED:
                print("\n\tSending underperformance email alert...")
                self.send_underperformance_alert(target_date, underperformers, daily_production)
        else:
            print("✓ All inverters performing within expected range")
        
        # Write to local CSV
        print("\nWriting to local CSV...")
        written = self.write_to_local_csv(target_date, daily_totals, daily_production, underperformers)
        
        # Write to Google Sheets only if local CSV was written
        if written and self.sheets_enabled:
            print("\nWriting to Google Sheets...")
            self.write_to_google_sheets(target_date, daily_totals, daily_production, underperformers)
        elif not written:
            print("\nSkipping Google Sheets (duplicate date)")
        
        # Check if it's the first day of the month
        if target_date.day == 1 and EMAIL_ENABLED:
            print("\n📅 First day of month - sending monthly summary...")
            self.send_monthly_summary(target_date)
        
        print("\n✓ Daily summary completed!")

if __name__ == '__main__':
    # Check if running in virtual environment
    if sys.prefix == sys.base_prefix:
        print("⚠️  WARNING: Not running in virtual environment!")
        print("   Run: source venv/bin/activate")
        print()

    summary = DailySolarSummary()
    
    # Check for test email flag
    if len(sys.argv) > 1 and sys.argv[1] == '--test-email':
        if not EMAIL_ENABLED:
            print("❌ Email not configured. Check config.py settings.")
            sys.exit(1)
        
        print("\tTesting email configuration...")
        print(f"SMTP Server: {SMTP_SERVER}:{SMTP_PORT}")
        print(f"From: {EMAIL_FROM}")
        print(f"To: {SUPERVISOR_EMAIL}")
        print("\nSending test email...")
        
        test_html = """
        <html>
        <body>
            <h2>Solar Monitor - Email Test</h2>
            <p>This is a test email from your solar monitoring system.</p>
            <p>If you received this, your email configuration is working correctly!</p>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th>Setting</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>SMTP Server</td>
                    <td>{}</td>
                </tr>
                <tr>
                    <td>From Address</td>
                    <td>{}</td>
                </tr>
                <tr>
                    <td>To Address</td>
                    <td>{}</td>
                </tr>
            </table>
        </body>
        </html>
        """.format(f"{SMTP_SERVER}:{SMTP_PORT}", EMAIL_FROM, SUPERVISOR_EMAIL)
        
        success = summary.send_email("☀️ Solar Monitor - Test Email", test_html)
        
        if success:
            print("\n\t✓ Test email sent successfully!")
            print("Check your inbox (and spam folder).")
        else:
            print("\n\t❌ Failed to send test email.")
            print("Check your config.py settings and app-specific password.")
        
        sys.exit(0)
    
    # Check for test monthly email flag with real data
    if len(sys.argv) > 1 and sys.argv[1].startswith('--test-'):
        month_abbr = sys.argv[1].replace('--test-', '').upper()
        
        # Map month abbreviations to numbers
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        
        if month_abbr == 'MONTHLY':
            # Already handled above
            pass
        elif month_abbr in month_map:
            if not EMAIL_ENABLED:
                print("❌ Email not configured. Check config.py settings.")
                sys.exit(1)
            
            if not DAILY_SUMMARY_CSV.exists():
                print(f"❌ No data file found: {DAILY_SUMMARY_CSV}")
                sys.exit(1)
            
            target_month = month_map[month_abbr]
            
            print(f"Testing monthly summary email for {month_abbr} using real data...")
            print(f"Reading from: {DAILY_SUMMARY_CSV}")
            
            # Find all years with data for this month
            monthly_data_by_year = defaultdict(list)
            
            with open(DAILY_SUMMARY_CSV, 'r') as f:
                reader = csv.DictReader(f)
                # Get column names from first row
                first_row = True
                for row in reader:
                    if first_row:
                        print(f"CSV columns: {list(row.keys())}")
                        first_row = False
                    date = datetime.strptime(row['Date'], '%Y-%m-%d').date()
                    if date.month == target_month:
                        monthly_data_by_year[date.year].append(row)
            
            if not monthly_data_by_year:
                print(f"❌ No data found for {month_abbr} in {DAILY_SUMMARY_CSV}")
                sys.exit(1)
            
            # Use the most recent year as target
            latest_year = max(monthly_data_by_year.keys())
            month_data = monthly_data_by_year[latest_year]
            
            print(f"Found data for {month_abbr} in years: {sorted(monthly_data_by_year.keys())}")
            print(f"Using {month_abbr} {latest_year} as target month")
            print(f"Days of data: {len(month_data)}")
            
            # Get lifetime value
            lifetime_pv = None
            if month_data and month_data[-1].get('Lifetime PV (kWh)'):
                lifetime_pv = float(month_data[-1]['Lifetime PV (kWh)'])
            
            # Build lifetime info for subject line
            lifetime_str = f" | Lifetime: {lifetime_pv:.0f} kWh" if lifetime_pv else ""
            
            # Create target_date for formatting
            target_date = datetime(latest_year, target_month, 1).date()
            
            # Build Year-over-Year comparison table with all years
            yoy_table = """
            <h3>Year-over-Year Comparison</h3>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th>Year</th>
                    <th>Average Daily Production (kWh)</th>
                    <th>Monthly PV Production (kWh)</th>
                    <th>Monthly Site Consumption (kWh)</th>
                    <th>Monthly Net Grid (kWh)</th>
                </tr>
            """
            
            # Sort years in descending order
            for year in sorted(monthly_data_by_year.keys(), reverse=True):
                year_data = monthly_data_by_year[year]
                
                # Calculate totals, handling empty values
                total_pv = sum(float(row['Daily PV Production (kWh)']) if row.get('Daily PV Production (kWh)') else 0.0 for row in year_data)
                total_consumption = sum(float(row['Daily Site Consumption (kWh)']) if row.get('Daily Site Consumption (kWh)') else 0.0 for row in year_data)
                total_net = sum(float(row['Daily Net Grid (kWh)']) if row.get('Daily Net Grid (kWh)') else 0.0 for row in year_data)
                days_reporting = len(year_data)
                avg_daily = (total_pv / days_reporting) if days_reporting > 0 else 0
                
                # Format values, show ? for zero values
                avg_daily_str = f"{avg_daily:.1f}" if avg_daily > 0 else "?"
                total_pv_str = f"{total_pv:.1f}" if total_pv > 0 else "?"
                total_consumption_str = f"{total_consumption:.1f}" if total_consumption > 0 else "?"
                total_net_str = f"{total_net:.1f}" if total_net > 0 else "?"
                
                yoy_table += f"""
                <tr>
                    <td><strong>{year}</strong></td>
                    <td>{avg_daily_str}</td>
                    <td>{total_pv_str}</td>
                    <td>{total_consumption_str}</td>
                    <td>{total_net_str}</td>
                </tr>
                """
            
            yoy_table += "</table>"
            
            # Build daily data table
            daily_table = """
            <h3>Daily Breakdown</h3>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th>Date</th>
                    <th>PV Production (kWh)</th>
                    <th>Site Consumption (kWh)</th>
                    <th>Net Grid (kWh)</th>
                    <th>Alerts</th>
                </tr>
            """
            
            for row in month_data:
                alert_cell = row.get('Alerts', '')
                alert_style = ' style="background-color: #fff3cd;"' if alert_cell else ''
                
                # Handle empty values
                pv_val = float(row['Daily PV Production (kWh)']) if row.get('Daily PV Production (kWh)') else 0.0
                consumption_val = float(row['Daily Site Consumption (kWh)']) if row.get('Daily Site Consumption (kWh)') else 0.0
                net_val = float(row['Daily Net Grid (kWh)']) if row.get('Daily Net Grid (kWh)') else 0.0
                
                daily_table += f"""
                <tr{alert_style}>
                    <td>{row['Date']}</td>
                    <td>{pv_val:.1f}</td>
                    <td>{consumption_val:.1f}</td>
                    <td>{net_val:.1f}</td>
                    <td>{alert_cell}</td>
                </tr>
                """
            
            daily_table += "</table>"
            
            # Build complete HTML email
            html = f"""
            <html>
            <body>
                <h2>Monthly Solar Summary - {target_date.strftime('%B %Y')} (TEST with REAL DATA)</h2>
                <p><em style="color: blue;">This is a test email using real data from {DAILY_SUMMARY_CSV}</em></p>
                
                {yoy_table}
                
                {daily_table}
                
                <p style="margin-top: 20px; color: #666; font-size: 0.9em;">
                    This is an automated monthly summary from your solar monitoring system.
                </p>
            </body>
            </html>
            """
            
            success = summary.send_email(
                f"☀️ Solar Monthly Summary - {target_date.strftime('%B %Y')}{lifetime_str} (TEST)", 
                html
            )
            
            if success:
                print("\n\t✓ Test monthly email sent successfully!")
                print("Check your inbox to review the layout and style with real data.")
            else:
                print("\n\t❌ Failed to send test email.")
            
            sys.exit(0)
        else:
            print(f"Unknown test option: {sys.argv[1]}")
            print("Usage: --test-JAN, --test-FEB, --test-MAR, etc.")
            sys.exit(1)
    
    # Check for test monthly email flag
    if len(sys.argv) > 1 and sys.argv[1] == '--test-monthly':
        if not EMAIL_ENABLED:
            print("❌ Email not configured. Check config.py settings.")
            sys.exit(1)
        
        print("Testing monthly summary email with simulated data...")
        
        # Generate fake monthly data
        import random
        from datetime import date
        
        target_date = date.today().replace(day=1)  # First of current month
        
        # Create simulated month data
        fake_month_data = []
        days_in_month = 30
        
        for day in range(1, days_in_month + 1):
            date_str = f"{target_date.year}-{target_date.month:02d}-{day:02d}"
            
            # Simulate varying daily production (15-25 kWh, with some cloudy days)
            base_production = 20.0
            variation = random.uniform(-5, 5)
            # Some days are cloudy
            if random.random() < 0.2:  # 20% chance of cloudy day
                variation -= random.uniform(5, 10)
            
            daily_pv = max(5.0, base_production + variation)
            daily_consumption = random.uniform(18, 28)
            daily_net = daily_consumption - daily_pv
            
            # Add alert to a few days
            alert = ""
            if day in [7, 15, 23]:  # Simulate problems on these days
                alert = f"⚠️ E00121950007846 ({random.randint(45, 75)}%)"
            
            fake_month_data.append({
                'Date': date_str,
                'Daily PV Production (kWh)': f"{daily_pv:.1f}",
                'Daily Site Consumption (kWh)': f"{daily_consumption:.1f}",
                'Daily Net Grid (kWh)': f"{daily_net:.1f}",
                'Alerts': alert
            })
        
        # Simulate lifetime value
        lifetime_pv = 27868.0
        lifetime_str = f" | Lifetime: {lifetime_pv:.0f} kWh"
        
        # Build Year-over-Year comparison table with simulated multi-year data
        yoy_table = """
        <h3>Year-over-Year Comparison</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f0f0f0;">
                <th>Year</th>
                <th>Average Daily Production (kWh)</th>
                <th>Monthly PV Production (kWh)</th>
                <th>Monthly Site Consumption (kWh)</th>
                <th>Monthly Net Grid (kWh)</th>
            </tr>
        """
        
        # Simulate data for current year and previous 2 years
        for year_offset in range(0, 3):
            year = target_date.year - year_offset
            
            # Simulate varying performance across years
            base_monthly = 600.0
            variation = random.uniform(-100, 100)
            total_pv = base_monthly + variation
            total_consumption = random.uniform(550, 700)
            total_net = total_consumption - total_pv
            avg_daily = total_pv / 30
            
            yoy_table += f"""
            <tr>
                <td><strong>{year}</strong></td>
                <td>{avg_daily:.1f}</td>
                <td>{total_pv:.1f}</td>
                <td>{total_consumption:.1f}</td>
                <td>{total_net:.1f}</td>
            </tr>
            """
        
        yoy_table += "</table>"
        
        # Build daily data table
        daily_table = """
        <h3>Daily Breakdown</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f0f0f0;">
                <th>Date</th>
                <th>PV Production (kWh)</th>
                <th>Site Consumption (kWh)</th>
                <th>Net Grid (kWh)</th>
                <th>Alerts</th>
            </tr>
        """
        
        for row in fake_month_data:
            alert_cell = row.get('Alerts', '')
            alert_style = ' style="background-color: #fff3cd;"' if alert_cell else ''
            
            daily_table += f"""
            <tr{alert_style}>
                <td>{row['Date']}</td>
                <td>{float(row['Daily PV Production (kWh)']):.1f}</td>
                <td>{float(row['Daily Site Consumption (kWh)']):.1f}</td>
                <td>{float(row['Daily Net Grid (kWh)']):.1f}</td>
                <td>{alert_cell}</td>
            </tr>
            """
        
        daily_table += "</table>"
        
        # Build complete HTML email
        html = f"""
        <html>
        <body>
            <h2>Monthly Solar Summary - {target_date.strftime('%B %Y')} (TEST DATA)</h2>
            <p><em style="color: red;">This is a test email with simulated data</em></p>
            
            {yoy_table}
            
            {daily_table}
            
            <p style="margin-top: 20px; color: #666; font-size: 0.9em;">
                This is an automated monthly summary from your solar monitoring system.
            </p>
        </body>
        </html>
        """
        
        success = summary.send_email(
            f"☀️ Solar Monthly Summary - {target_date.strftime('%B %Y')}{lifetime_str} (TEST)", 
            html
        )
        
        if success:
            print("\n\t✓ Test monthly email sent successfully!")
            print("Check your inbox to review the layout and style.")
        else:
            print("\n\t❌ Failed to send test email.")
        
        sys.exit(0)
    
    # Check if testing mode (can specify days ago)
    if len(sys.argv) > 1:
        try:
            days_ago = int(sys.argv[1])
            summary.run(days_ago=days_ago)
        except ValueError:
            print("Usage: python daily-solar-summary.py [days_ago] | --test-email | --test-monthly")
            sys.exit(1)
    else:
        summary.run(days_ago=1)  # Default: yesterday