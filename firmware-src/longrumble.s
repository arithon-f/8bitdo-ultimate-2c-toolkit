@ SPDX-License-Identifier: GPL-3.0-or-later
@ Long rumble over Bluetooth (controller firmware 1.09, with bt_xbox and bt_rumble).
@
@ An Xbox rumble request has a duration (10 ms units, at most 255) and a loop count: the motors run for the duration,
@ then loop-count times more. rumble_write passes the duration to motor_set (0xfa68) as its hold and ignores the loop
@ count, and in Bluetooth mode the main loop calls motor_set(0, 0, 0) on every pass (0xa4ae), which switches the
@ motors off once the hold has run out: a request lasted at most 2.55 s. Linux and Android's hid-microsoft asks once
@ for a long rumble (duration 255, loop count 255) and sends nothing more until the strength changes, so on Android a
@ long rumble stopped after 2.55 s; SDL resends every 2 s, so macOS never noticed.
@
@ Here the loop count is honoured, as on an Xbox controller: duration * (loop count + 1), at most 652.8 s. The host's
@ next request (its stop included), one of the controller's own buzzes (holds 20 and 150) or a disconnection ends it
@ sooner. The start delay is still ignored. Nothing here depends on the Home ring's code.
@
@ ARM Thumb-1, converted to TC32 by firmware-src/longrumble.py, which also builds the two hooks and the callback pointer.

        .syntax unified
        .thumb
        .text

        .equ HERE,         0x1734C    @ where recipes.py places this code: the stock Report Map, unused once bt_xbox
                                      @ points the Report Map attribute (0x177a8) at its own map at 0x18274
        .equ RUMBLE_WRITE, 0x18390    @ bt_rumble's rumble_write, which the write callback pointed at
        .equ STRONG,       0x8434EF   @ motor_set's strong (u8); +1 weak; +2 hold (u8, 10 ms ticks, counted down by
                                      @ the motor routine 0xfaa0); ours: +3 the duration to repeat, +4 the repeats left,
                                      @ alignment padding before the motor routine's u32 timestamp at 0x8434f4 that
                                      @ nothing else reads or writes
        .equ CONNECTED,    0x8436BC   @ 1 from the Bluetooth connect callback (0xa0ea), 0 from the disconnect one
                                      @ (0xa074); stock_connected_bt (0xa28c) reads it

@ Hook A, at 0xfa72 instead of "lsls r2, r2, #24; lsrs r2, r2, #24": r0 strong, r1 weak (already u8), r2 the hold as
@ passed. Returns r2 = hold & 0xff, as the two shifts did, with r0 and r1 kept. r3 and r4 are free: motor_set pushed
@ r4, and both of its paths load r3 and r4 before using them.
long_hold:
        lsls    r2, r2, #24
        lsrs    r2, r2, #24
        cmp     r2, #0
        beq     1f                  @ a zero-hold call: rearm decides
        ldr     r3, =STRONG
        movs    r4, #0
        strb    r4, [r3, #4]        @ any set with a hold ends the repeats: a buzz, a stop, a new request, whose own
1:      bx      lr                  @ repeats long_write sets afterwards

@ Hook B, at 0xfa88 instead of "ldr r3, =STRONG + 2; ldrb r4, [r3]": a zero-hold call, r0 strong, r1 weak, r2 = 0.
@ Returns r3 = the hold's address, and r4 = 0 for motor_set to take the call (store r0, r1 and hold 0) or nonzero for
@ it to ignore the call, with r0, r1 and r2 kept.
rearm:
        ldr     r3, =STRONG
        adds    r3, #2
        ldrb    r4, [r3]
        cmp     r4, #0
        bne     9f                  @ a hold is running: ignored, as in stock
        push    {r0, r1}
        ldrb    r1, [r3, #2]        @ repeats left
        cmp     r1, #0
        beq     8f                  @ none: the call goes through (r4 = 0)
        ldr     r0, =CONNECTED
        ldrb    r0, [r0]
        cmp     r0, #0
        beq     7f                  @ the host is gone: drop them, and the call goes through
        subs    r1, #1
        strb    r1, [r3, #2]
        ldrb    r4, [r3, #1]        @ the duration again (at least 1); the motors keep their strengths
        strb    r4, [r3]
        b       8f                  @ r4 nonzero: the call is ignored
7:      strb    r4, [r3, #2]        @ r4 = 0
8:      pop     {r0, r1}
9:      bx      lr

@ The output report's write callback (the pointer at 0x17764): rumble_write as before; then, if that was a rumble with
@ a motor on and the write carries the loop count (value byte 7), the repeats for rearm.
long_write:
        push    {r4, lr}
        adds    r4, r0, #0          @ Telink's ATT write: L2CAP length at [2..3], the value from [9]
        bl      long_hold + (RUMBLE_WRITE - HERE)
        ldrb    r1, [r4, #2]        @ the length's low byte: a rumble write is far below 256
        cmp     r1, #3 + 8          @ opcode + handle + 8 value bytes, the loop count included
        blt     1f
        ldrb    r1, [r4, #9]        @ the enable mask
        cmp     r1, #0x80
        bhs     1f                  @ bit 7: a Home ring command, not a rumble
        ldr     r3, =STRONG
        ldrb    r1, [r3]            @ the strengths rumble_write set (after the settings' intensity, if installed)
        ldrb    r2, [r3, #1]
        orrs    r1, r2
        beq     1f                  @ both motors off: a stop
        ldrb    r1, [r4, #9 + 7]    @ the loop count
        strb    r1, [r3, #4]
        ldrb    r1, [r3, #2]        @ the duration rumble_write set as the hold (at least 1)
        strb    r1, [r3, #3]
1:      movs    r0, #0
        pop     {r4, pc}

        .balign 4
code_end:
        .ltorg
