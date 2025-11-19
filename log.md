# Project Log, in reverse chronological order

## 18 Nov 2025

- [kind feedback from @rbgirshick](https://github.com/steveturbek/SunPower-PVS-Supervisor/issues/1)
- Issue accessing raspberry pi via SSH. A reboot fixed it.

**Problem:** SSH timeouts after long uptime, ping works, reboot fixes it

**Fix:**

```bash
# Create /etc/rc.local
sudo nano /etc/rc.local
```

```bash
#!/bin/bash
/sbin/iwconfig wlan0 power off
exit 0
```

```bash
# Make executable
sudo chmod +x /etc/rc.local

# Verify
iwconfig wlan0 | grep "Power Management"
# Should show: Power Management:off
```

**Test after reboot:** `iwconfig wlan0` should show `Power Management:off`

## 30 Sep 2025

- updated code, testing on home
- learned new VarServer technique, published how to to reddit and readme
- lots of research

## 15 Sept 2025

- Initial Raspberry Pi setup completed. See README.md for current setup instructions.
