#!/usr/bin/env python3

import requests
import json
import sys

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
        
        # Find all inverter devices
        inverters = []
        for device in data.get('devices', []):
            descr = device.get('DESCR', '')
            if 'Inverter' in descr:
                state_descr = device.get('STATEDESCR', 'Unknown')
                inverters.append((descr, state_descr))
        
        # Display results
        if inverters:
            print(f"\nFound {len(inverters)} inverters:")
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
