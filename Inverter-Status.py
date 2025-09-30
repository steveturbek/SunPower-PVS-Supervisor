#!/usr/bin/env python3

import requests
import json
import sys
import base64
from datetime import datetime

# Import config
try:
    from config import PVS6_IP, PVS6_SERIAL_LAST5
except ImportError:
    print("Error: config.py not found. Copy config.py.example to config.py and add your values.")
    sys.exit(1)

def get_inverter_status():
    """
    Query PVS6 device and display status of all inverters using VASERVER API
    """
    # Create session with cookies
    session = requests.Session()
    
    # Create basic auth header
    auth_string = f"ssm_owner:{PVS6_SERIAL_LAST5}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
    
    base_url = f"https://{PVS6_IP}"
    headers = {"Authorization": f"Basic {auth_b64}"}
    
    try:
        # Step 1: Login
        print("Authenticating with PVS6...")
        login_response = session.get(
            f"{base_url}/auth?login",
            headers=headers,
            verify=False,
            timeout=10
        )
        login_response.raise_for_status()
        
        # Step 2: Get all data
        print("Querying PVS6 device...")
        data_response = session.get(
            f"{base_url}/vars?match=/&fmt=obj",
            verify=False,
            timeout=10
        )
        data_response.raise_for_status()
        
        # Parse JSON response
        data = data_response.json()
        
        # Extract livedata summary
        pv_p = float(data.get('/sys/livedata/pv_p', 0))
        pv_en = float(data.get('/sys/livedata/pv_en', 0))
        net_p = float(data.get('/sys/livedata/net_p', 0))
        site_load_p = float(data.get('/sys/livedata/site_load_p', 0))
        
        # Get production meter power for comparison
        production_meter_power = float(data.get('/sys/devices/meter/0/p3phsumKw', 0))
        
        # Find all inverters and their power
        inverters = []
        total_inverter_power = 0.0
        inverter_index = 0
        
        while True:
            inverter_key = f'/sys/devices/inverter/{inverter_index}/sn'
            if inverter_key not in data:
                break
            
            serial = data.get(inverter_key, 'Unknown')
            power = float(data.get(f'/sys/devices/inverter/{inverter_index}/p3phsumKw', 0))
            energy = float(data.get(f'/sys/devices/inverter/{inverter_index}/ltea3phsumKwh', 0))
            
            inverters.append({
                'serial': serial,
                'power': power,
                'energy': energy
            })
            total_inverter_power += power
            inverter_index += 1
        
        # Display results
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Check data freshness - parse the meter timestamp
        meter_time_str = data.get('/sys/devices/meter/0/msmtEps', '')
        data_is_old = False
        if meter_time_str:
            try:
                meter_time = datetime.strptime(meter_time_str, '%Y-%m-%dT%H:%M:%SZ')
                now = datetime.utcnow()
                minutes_old = (now - meter_time).total_seconds() / 60
                if minutes_old > 15:  # Data older than 15 minutes
                    data_is_old = True
            except ValueError:
                pass
        
        old_flag = " !OLD" if data_is_old else ""
        
        # Check if system is producing
        if pv_p == 0 and total_inverter_power == 0:
            print(f"\n⚠️  No solar production detected at {timestamp}")
            print("This is normal at night or on very cloudy days.")
            print(f"Lifetime production: {pv_en:.1f} kWh{old_flag}")
            return
        
        print(f"\n=== Solar System Status at {timestamp} ===")
        print(f"PV Production:  {pv_p:.3f} kW  (Lifetime: {pv_en:.1f} kWh)")
        print(f"Net Power:      {net_p:.3f} kW  {'(exporting to grid)' if net_p < 0 else '(importing from grid)'}")
        print(f"Site Load:      {site_load_p:.3f} kW")
        print()
        
        if inverters:
            # Power comparison
            difference = abs(total_inverter_power - production_meter_power)
            percentage_diff = (difference / production_meter_power * 100) if production_meter_power > 0 else 0
            
            print(f"Found {len(inverters)} inverters | Meter: {production_meter_power:.3f}kW | Sum: {total_inverter_power:.3f}kW | Diff: {difference:.3f}kW ({percentage_diff:.1f}%)")
            print("-" * 80)
            for i, inv in enumerate(inverters, 1):
                print(f'{i:2d}. {inv["serial"]}: {inv["power"]:.3f} kW  (Lifetime: {inv["energy"]:.1f} kWh)')
        else:
            print("⚠️  No inverters found in response")
            
    except requests.exceptions.Timeout:
        print("Error: Request timed out. Is the PVS6 device accessible?")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to PVS6 device. Check network connection and config.py settings.")
    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}")
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from PVS6")
    except KeyError as e:
        print(f"Error: Unexpected data format - missing key {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    # Disable SSL warnings for self-signed cert
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    get_inverter_status()