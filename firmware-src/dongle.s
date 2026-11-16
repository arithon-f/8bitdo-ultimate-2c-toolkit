@ SPDX-License-Identifier: GPL-3.0-or-later
@ The 2.4 GHz dongle's D-input mode (dongle firmware 1.03), as its factory firmware 1.00 had it. The controller marks its
@ packets 0x8f once it's set to D-input with B + Home; at link-up 1.00 then came up as the D-input gamepad 2dc8:301c,
@ while 1.03 always comes up as X-input. 1.03 kept the mode, its descriptors and its reports, but not this check.
@ Linked on its own at 0xff48, in the zeros after the image (build.sh, ops/dongle.py), with 1.03's addresses:
@ reenum 0xdc9c (200 ms disconnect, then reconnect with the mode's descriptors), init_idle 0xddf8, init_xinput 0xde28.

@ The link-up handler (RAM code at 0x940, image 0x6940) calls this instead of init_usb_xinput. The D-input branch is
@ 1.00's setter (its image 0xaae4) with 1.03's variables.
	.text
link_mode:
	tpush	{lr}
	tloadr	r0, .Lrf_type
	tloadrb	r0, [r0, #0]
	tcmp	r0, #0x8f
	tjne	.Lxinput
	tloadr	r0, .Lpairing
	tloadrb	r0, [r0, #0]
	tcmp	r0, #0
	tjne	.Lidle
	tloadr	r0, .Lusb_mode
	tloadrb	r1, [r0, #0]
	tcmp	r1, #1
	tjeq	.Ldone
	tmovs	r1, #1
	tstorerb	r1, [r0, #0]
	tjl	reenum
.Ldone:	tpop	{pc}
.Lidle:	tjl	init_idle
	tpop	{pc}
.Lxinput:
	tjl	init_xinput
	tpop	{pc}

	.balign	4
.Lrf_type:
	.word	0x843108	@ first byte of the controller's last packet: 0x8f asks for D-input
.Lpairing:
	.word	0x842f14	@ nonzero: the dongle stays idle
.Lusb_mode:
	.word	0x842d41	@ 0 X-input, 1 D-input, 4 idle
