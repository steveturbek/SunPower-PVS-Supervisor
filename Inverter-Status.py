#!/usr/bin/env python3

import requests
import json
import sys
from datetime import datetime

def parse_pvs6_time(time_str):
    """Parse PVS6 time format: '2025,08,27,15,07,18' to datetime object"""
    if not time_str:
        return None
    try:
        parts = time_str.split(',')
        if len(parts) == 6:
            year, month, day, hour, minute, second = map(int, parts)
            return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        pass
    return None

def get_time_diff_text(current_time_str, data_time_str):
    """
    Calculate time difference and return formatted string
    Returns 'NEW' if < 1 minute, otherwise '>Xm', '>Xh', or '>Xd'
    """
    current_time = parse_pvs6_time(current_time_str)
    data_time = parse_pvs6_time(data_time_str)
    
    if not current_time or not data_time:
        return "?"
    
    # Calculate difference in seconds
    diff_seconds = (current_time - data_time).total_seconds()
    
    if diff_seconds < 0:
        return "FUTURE"  # Data time is in future
    
    if diff_seconds < 60:
        return "NEW"
    elif diff_seconds < 3600:  # Less than 1 hour
        minutes = int(diff_seconds // 60)
        return f">{minutes}m"
    elif diff_seconds < 86400:  # Less than 1 day
        hours = int(diff_seconds // 3600)
        return f">{hours}h"
    else:  # 1 day or more
        days = int(diff_seconds // 86400)
        return f">{days}d"

def get_inverter_status():
    """
    Query PVS6 device and display status of all inverters
    Meant to be run from a Raspberry Pi connected to ethernet LAN port in PVS6
    """
    url = "http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList"
    
    try:
        # Make the HTTP request
        print("Querying PVS6 device...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Parse JSON response
        data = response.json()
        
        # Check if we got a successful result
        if data.get('result') != 'succeed':
            print(f"Error: PVS6 returned result: {data.get('result')}")
            return
        
        # Find current time from PVS device for time difference calculations
        current_time = None
        for device in data.get('devices', []):
            if device.get('DEVICE_TYPE') == 'PVS':
                current_time = device.get('CURTIME', '')
                break
        
        # Find all inverter devices
        inverters = []
        for device in data.get('devices', []):
            if device.get('DEVICE_TYPE') == 'Inverter':
                serial = device.get('SERIAL', 'Unknown')
                descr = device.get('DESCR', f'Inverter {serial}')
                state = device.get('STATE', 'Unknown')
                state_descr = device.get('STATEDESCR', 'Unknown')
                data_time = device.get('DATATIME', '')
                # Get AC power, handle string/float conversion
                try:
                    ac_power = float(device.get('p_3phsum_kw', 0))
                except (ValueError, TypeError):
                    ac_power = 0.0
                
                # Add power info for working inverters, time diff for error states
                status_info = state_descr
                if state.lower() == 'working':
                    # Add current AC power production for working inverters
                    status_info += f" {ac_power:.3f}kW"
                elif state.lower() == 'error':
                    # Add time difference for error states
                    if current_time and data_time:
                        time_diff = get_time_diff_text(current_time, data_time)
                        status_info += f" [{time_diff}]"
                    elif data_time:
                        status_info += " [?]"
                    else:
                        status_info += " [NO DATA]"
                
                inverters.append((descr, status_info))
        
        # Display results
        if inverters:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\nFound {len(inverters)} inverters at {timestamp}:")
            print("-" * 60)
            for i, (descr, state) in enumerate(inverters, 1):
                print(f'{i:2d}. {descr}: {state}')
        else:
            print("No inverters found in response")
            
    except requests.exceptions.Timeout:
        print("Error: Request timed out. Is the PVS6 device accessible?")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to PVS6 device. Check network connection.")
    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}")
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from PVS6")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    get_inverter_status()