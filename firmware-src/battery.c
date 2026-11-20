// SPDX-License-Identifier: GPL-3.0-or-later
/* The battery percentage from a measured discharge (2026-11-20: 33.6 h switched on, from a full charge to 3300 mV, where
 * the controller turns itself off): the share of that time still left at each voltage, every 64 mV from 3288 mV (4120 mV, just under a full charge's 4129, reads 100),
 * interpolated. Stock's 0xb5a8 maps 3499-4100 mV linearly, so it showed 50 % with 72 % of the time left and 1 % for the
 * last 7 hours. 0xb5a8 calls this with the voltage (0x843424) instead of its formula; its own code around the call still
 * floors the result at 1 % and moves it only down on battery and only up while charging. Build: build.sh; test: test.py. */
typedef unsigned char u8;
typedef unsigned int u32;

static const u8 PCT_AT[15] = {0, 1, 8, 15, 27, 47, 57, 64, 72, 78, 84, 90, 95, 100, 100};

u32 battery_pct(u32 mv)
{
	u32 d, i;

	if (mv <= 3288)
		return 0;
	d = mv - 3288;
	i = d >> 6;
	if (i >= 14)
		return 100;
	return PCT_AT[i] + ((PCT_AT[i + 1] - PCT_AT[i]) * (d & 63) >> 6);
}
