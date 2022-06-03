from ophyd import EpicsMotor, Device, Component as Cpt


class MaiaStage(Device):
    x    = Cpt(EpicsMotor, '{X12:1-Ax:X}Mtr')
    y    = Cpt(EpicsMotor, '{X12:1-Ax:Y}Mtr')

M = MaiaStage('XF:04BM-ES:2', name='M')
M_x   = M.x
M_y   = M.y
