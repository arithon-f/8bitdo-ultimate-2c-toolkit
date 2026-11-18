    .text
    .global rumble
rumble:
    tloadrb r0, [r4, #12]
    tloadrb r2, [r4, #10]
    tcmp    r0, r2
    tjcs    left_max
    tmov    r0, r2
left_max:
    tloadrb r1, [r4, #13]
    tloadrb r2, [r4, #11]
    tcmp    r1, r2
    tjcs    right_max
    tmov    r1, r2
right_max:
    tmovs   r3, #164
    tmul    r0, r3
    tshftr  r0, r0, #6
    tcmp    r0, #255
    tjls    left_ok
    tmovs   r0, #255
left_ok:
    tmul    r1, r3
    tshftr  r1, r1, #6
    tcmp    r1, #255
    tjls    right_ok
    tmovs   r1, #255
right_ok:
    tjex    lr
