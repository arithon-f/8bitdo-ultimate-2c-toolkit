@ SPDX-License-Identifier: GPL-3.0-or-later
@ The 2.4 GHz dongle's D-input mode (dongle firmware 1.03), as its factory firmware 1.00 had it. The controller marks its
@ packets 0x8f once it's set to D-input with B + Home; at link-up 1.00 then came up as the D-input gamepad 2dc8:301c,
@ while 1.03 always comes up as X-input. 1.03 kept the mode, its descriptors and its reports, but not this check.
@ ARM Thumb-1, converted to TC32 by firmware-src/dongle.py. Placed in the zeros after the image (ops/dongle.py).

        .syntax unified
        .thumb
        .text

        .equ HERE,        0xFF48      @ where ops/dongle.py places this code
        .equ RF_TYPE,     0x843108    @ first byte of the controller's last packet: 0x8f asks for D-input
        .equ PAIRING,     0x842F14    @ nonzero: the dongle stays idle
        .equ USB_MODE,    0x842D41    @ 0 X-input, 1 D-input, 4 idle
        .equ REENUM,      0xDC9C      @ 200 ms disconnect, then reconnect with USB_MODE's descriptors
        .equ INIT_IDLE,   0xDDF8
        .equ INIT_XINPUT, 0xDE28

@ The link-up handler (RAM code at 0x940, image 0x6940) calls this instead of init_usb_xinput. The D-input branch is
@ 1.00's setter (its image 0xaae4) with 1.03's variables.
link_mode:
        push    {lr}
        ldr     r0, =RF_TYPE
        ldrb    r0, [r0]
        cmp     r0, #0x8F
        bne     xinput
        ldr     r0, =PAIRING
        ldrb    r0, [r0]
        cmp     r0, #0
        bne     idle
        ldr     r0, =USB_MODE
        ldrb    r1, [r0]
        cmp     r1, #1
        beq     done
        movs    r1, #1
        strb    r1, [r0]
        bl      link_mode + (REENUM - HERE)
done:   pop     {pc}
idle:   bl      link_mode + (INIT_IDLE - HERE)
        pop     {pc}
xinput: bl      link_mode + (INIT_XINPUT - HERE)
        pop     {pc}

        .balign 4
code_end:
        .ltorg
