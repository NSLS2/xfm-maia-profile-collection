import copy
import queue
import traceback
from dataclasses import asdict, dataclass, fields
from enum import Enum
from multiprocessing import Pipe, Process, Value
from typing import Optional
from unittest.mock import Mock
import builtins
import sys

import bluesky.plan_stubs as bps
import pandas as pd
from bluesky.run_engine import RunEngine
from ophyd import Component as Cpt
from ophyd import Device, EpicsMotor, EpicsSignalRO
from bluesky.utils import install_qt_kicker, RunEngineInterrupted

install_qt_kicker()
# from qtpy import QtCore, QtGui, QtWidgets
from matplotlib.backends.qt_compat import QtCore, QtGui, QtWidgets
from matplotlib.backends.backend_qt5 import _create_qApp
from qmicroscope.microscope import Microscope
from qmicroscope.plugins import CrossHairPlugin

def show_error_message(error_text="Error occured", error_title="Error"):
    msg = QtWidgets.QMessageBox()
    msg.setIcon(QtWidgets.QMessageBox.Critical)
    msg.setWindowTitle(error_title)
    msg.setText(error_text)
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg.exec_()

@dataclass
class SampleMetadata:
    info: str = ""
    # name: str = ""
    owner: str = ""
    serial: str = ""
    type: str = ""


@dataclass
class ScanMetadata:
    region: str = ""
    info: str = ""
    seq_num: str = ""
    seq_total: str = ""

@dataclass
class Position:
    x: float
    y: float
    z: float

@dataclass
class MaiaFlyDefinition:
    ystart: float
    ystop: float
    ypitch: float
    xstart: float
    xstop: float
    xpitch: float
    dwell: float
    name: str = ""
    md: "Optional[SampleMetadata | ScanMetadata]" = None


class RequestStatus(Enum):
    # Colors are tuple of values for (foreground, background)
    COLLECTING = (QtCore.Qt.GlobalColor.black, QtCore.Qt.GlobalColor.green) 
    COMPLETE = (QtCore.Qt.GlobalColor.black, QtCore.Qt.GlobalColor.cyan)
    QUEUED = (QtCore.Qt.GlobalColor.black, QtCore.Qt.GlobalColor.white)


class QueueItem:
    def __init__(self, label, data):
        self.label = label
        self.data = data
        self.status = RequestStatus.QUEUED


class QueueModel:
    def __init__(self):
        self.queue: list[QueueItem] = []

    def add_item(self, item):
        # Check if item label is empty
        if not item.label:
            raise ValueError("No label specified for item")
        # Check if new item has the same label as existing item
        for i in self.queue:
            if i.label == item.label:
                raise ValueError(f"Item with label {item.label} already exists")

        self.queue.append(item)

    def remove_item(self, index):
        if 0 <= index < len(self.queue):
            del self.queue[index]

    def move_item_up(self, index):
        if 1 <= index < len(self.queue):
            self.queue[index - 1], self.queue[index] = (
                self.queue[index],
                self.queue[index - 1],
            )

    def move_item_down(self, index):
        if 0 <= index < len(self.queue) - 1:
            self.queue[index + 1], self.queue[index] = (
                self.queue[index],
                self.queue[index + 1],
            )

    def get_items(self):
        return self.queue


class QueueWidget(QtWidgets.QWidget):
    queue_updated = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self.model = QueueModel()
        self.init_ui()

    def init_ui(self):
        self.setLayout(QtWidgets.QVBoxLayout())

        self.list_widget = QtWidgets.QListWidget()
        self.layout().addWidget(self.list_widget)

        # self.add_button = QtWidgets.QPushButton("Add Item")
        # self.add_button.clicked.connect(self.add_item)
        # self.layout().addWidget(self.add_button)

        self.remove_button = QtWidgets.QPushButton("Remove Item")
        self.remove_button.clicked.connect(self.remove_item)
        self.layout().addWidget(self.remove_button)

        self.up_button = QtWidgets.QPushButton("Move Up")
        self.up_button.clicked.connect(self.move_item_up)
        self.layout().addWidget(self.up_button)

        self.down_button = QtWidgets.QPushButton("Move Down")
        self.down_button.clicked.connect(self.move_item_down)
        self.layout().addWidget(self.down_button)
        self.list_widget.itemEntered.connect(self.show_tooltip)

    def show_tooltip(self, item):
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), item.toolTip())

    def add_item(self):
        """
        item, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add Item",
            "Enter item as a comma-separated tuple (e.g., 'value1,value2,value3,value4'):",
        )
        if ok:
            item_tuple = tuple(item.split(","))
            if len(item_tuple) == 4:
                self.model.add_item(item_tuple)
                self.update_list()
        """
        pass

    def remove_item(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            index = self.list_widget.row(selected_items[0])
            self.model.remove_item(index)
            self.update_list()

    def move_item_up(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            index = self.list_widget.row(selected_items[0])
            self.model.move_item_up(index)
            self.update_list()

    def move_item_down(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            index = self.list_widget.row(selected_items[0])
            self.model.move_item_down(index)
            self.update_list()

    def update_list(self):
        self.list_widget.clear()
        for item in self.model.get_items():
            list_item = QtWidgets.QListWidgetItem(str(item.label))
            text = """<table border='1' style='border-collapse: collapse;'>
            <tr>
            <th style='border: 1px solid black;'>Parameter</th>
            <th style='border: 1px solid black;'>Value</th>
            </tr>"""
            # for key, value in item.data[0].items():
            for field in fields(item.data):
                key = field.name
                value = getattr(item.data, key)

                text += f"""<tr><td style='border: 1px solid black;'>{key}</td>
                <td style='border: 1px solid black;'>{value}</td></tr>"""
            text = text + "</table>"
            list_item.setToolTip(text)
            list_item.setForeground(QtGui.QBrush(item.status.value[0]))
            list_item.setBackground(QtGui.QBrush(item.status.value[1]))
            self.list_widget.addItem(list_item)

        self.queue_updated.emit(self.model.get_items())


class SamplePositionQueueWidget(QueueWidget):
    go_to_position_signal = QtCore.Signal(object)

    def contextMenuEvent(self, event):
        # Find the item at the click position
        item = self.list_widget.itemAt(
            self.list_widget.mapFromGlobal(event.globalPos())
        )

        if item:
            # Create a context menu
            menu = QtWidgets.QMenu(self)

            # Add actions to the menu
            go_to_position_action = menu.addAction("Go to position")

            go_to_position_action.triggered.connect(
                lambda: self.emit_go_to_position(item)
            )

            # Execute the menu and get the selected action
            action = menu.exec_(event.globalPos())

    def emit_go_to_position(self, item):
        index = self.list_widget.indexFromItem(item).row()
        position_item = self.model.get_items()[index]
        self.go_to_position_signal.emit(position_item.data)

    def add_item(self, position_name, x, y, z):
        item = QueueItem(label=position_name, data=Position(x, y, z))
        try:
            self.model.add_item(item)
            self.update_list()
        except ValueError as e:
            show_error_message(str(e))


class CollectionQueueWidget(QueueWidget):
    selected_item_data_signal = QtCore.Signal(object, int)

    def contextMenuEvent(self, event):
        # Find the item at the click position
        item = self.list_widget.itemAt(
            self.list_widget.mapFromGlobal(event.globalPos())
        )

        if item:
            # Create a context menu
            menu = QtWidgets.QMenu(self)

            # Add actions to the menu
            edit_action = menu.addAction("Edit Request")
            # remove_action = menu.addAction("Remove")
            # move_up_action = menu.addAction("Move Up")
            # move_down_action = menu.addAction("Move Down")

            edit_action.triggered.connect(lambda: self.edit_item(item))

            # Execute the menu and get the selected action
            action = menu.exec_(event.globalPos())

    def edit_item(self, item):
        index = self.list_widget.indexFromItem(item).row()
        queue_item = self.model.get_items()[index]
        self.selected_item_data_signal.emit(queue_item.data, index)
    
    def set_status(self, item: QueueItem, status: RequestStatus):
        item.status = status
        self.update_list()

    def add_item(self, label, data: MaiaFlyDefinition):
        item = QueueItem(label=label, data=data)
        try:
            self.model.add_item(item)
        except ValueError as e:
            show_error_message(str(e))
        self.update_list()



class RunEngineState(str, Enum):
    idle = "idle"
    running = "running"
    paused = "paused"


def maia_plan(payload):
    def main_plan(payload):
        yield from fly_maia(
                ystart=payload.ystart,
                ystop=payload.ystop,
                ypitch=payload.ypitch,
                xstart=payload.xstart,
                xstop=payload.xstop,
                xpitch=payload.xpitch,
                dwell=payload.dwell,
                md=asdict(payload.md),
                hf_stage=M,
                maia=maia,
                print_params=True,
            )
    
    return (yield from main_plan(payload))

class RunEngineControls:
    def __init__(self, RE, GUI):
        self.RE = RE
        self.GUI = GUI

        self.widget = button_widget = QtWidgets.QWidget()
        button_layout = QtWidgets.QHBoxLayout()
        button_widget.setLayout(button_layout)

        self.label = label = QtWidgets.QLabel("Idle")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("QLabel {background-color: green; color: white}")
        button_layout.addWidget(label)

        # Run button to execute RE
        self.button_run = button_run = QtWidgets.QPushButton("Run")
        button_run.clicked.connect(self.run)
        button_layout.addWidget(button_run)

        # Run button to execute RE
        self.button_pause = button_pause = QtWidgets.QPushButton("Pause")
        button_pause.clicked.connect(self.pause)
        button_layout.addWidget(button_pause)

        self.info_label = info_label = QtWidgets.QLabel("Motors info")
        info_label.setAlignment(QtCore.Qt.AlignLeft)
        # label.setStyleSheet('QLabel {background-color: green; color: white}')
        button_layout.addWidget(info_label)
        

        self.RE.state_hook = self.handle_state_change
        self.handle_state_change(self.RE.state, None)
        self.current_request = None

    def run(self):
        pbar_manager = self.RE.waiting_hook
        self.RE.waiting_hook = None
        try:
            if self.RE.state == RunEngineState.paused:
                self.RE.resume()
                if self.current_request is not None:
                    self.GUI.queue_widget.set_status(self.current_request, RequestStatus.COMPLETE)
                    self.current_request = None
            # if self.RE.state == RunEngineState.idle:
            for item in self.GUI.queue_widget.model.get_items():
                self.current_request = item
                payload = item.data
                if item.status is not RequestStatus.COMPLETE:
                    self.GUI.queue_widget.set_status(item, RequestStatus.COLLECTING)
                    self.RE(
                        maia_plan(payload)
                    )
                    self.GUI.queue_widget.set_status(item, RequestStatus.COMPLETE)
        except RunEngineInterrupted:
            pass
        except Exception as e:
            print(f"{type(e).__name__}")
            print(f"Exception occured: {e}")
            self.current_request = None
        finally:
            self.RE.waiting_hook = pbar_manager
                

    def pause(self):
        if RunEngineState(self.RE.state) == RunEngineState.running:
            self.RE.request_pause()
        elif RunEngineState(self.RE.state) == RunEngineState.paused:
            self.RE.stop()

    def handle_state_change(self, new, old):
        if new == "idle":
            color = "green"
            button_run_enabled = True
            button_pause_enabled = False
            button_run_text = "Run"
            button_pause_text = "Pause"
        elif new == "paused":
            color = "blue"
            button_run_enabled = True
            button_pause_enabled = True
            button_run_text = "Resume"
            button_pause_text = "Stop"
        elif new == "running":
            color = "red"
            button_run_enabled = False
            button_pause_enabled = True
            button_run_text = "Run"
            button_pause_text = "Pause"
        else:
            color = "darkGray"
            button_run_enabled = False
            button_pause_enabled = False
            button_run_text = "Run"
            button_pause_text = "Stop"

        state = str(new).capitalize()
        
        self.update_state_ui(
            color,
            state,
            button_run_enabled,
            button_run_text,
            button_pause_enabled,
            button_pause_text,
        )

    def update_state_ui(
        self,
        color,
        state,
        button_run_enabled,
        button_run_text,
        button_pause_enabled,
        button_pause_text,
    ):
        #print("Updating UI")
        width = 60
        height = 60
        self.label.setFixedHeight(width)
        self.label.setFixedWidth(height)
        self.label.setStyleSheet(f"QLabel {{background-color: {color}; color: white}}")
        self.label.setText(state)

        self.button_run.setEnabled(button_run_enabled)
        self.button_run.setText(button_run_text)
        self.button_pause.setEnabled(button_pause_enabled)
        self.button_pause.setText(button_pause_text)


class SampleControlWidget(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__()

        # label = QtWidgets.QLabel("Sample control widget")
        self.setTitle("Sample Control")
        nudge_buttons = QtWidgets.QGridLayout()
        # nudge_buttons.addWidget(label)
        self.nudge_amount_spin_box = QtWidgets.QDoubleSpinBox()
        self.nudge_amount_spin_box.setValue(10)
        self.nudge_amount_spin_box.setMaximum(5000)
        self.nudge_amount_spin_box.setMinimum(0)

        up_button = QtWidgets.QToolButton()

        up_button.setArrowType(QtCore.Qt.ArrowType.UpArrow)
        up_button.clicked.connect(lambda: self.nudge("up"))

        down_button = QtWidgets.QToolButton()
        down_button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        down_button.clicked.connect(lambda: self.nudge("down"))

        left_button = QtWidgets.QToolButton()
        left_button.setArrowType(QtCore.Qt.ArrowType.LeftArrow)
        left_button.clicked.connect(lambda: self.nudge("left"))

        right_button = QtWidgets.QToolButton()
        right_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        right_button.clicked.connect(lambda: self.nudge("right"))

        focus_in_button = QtWidgets.QToolButton()
        focus_in_button.setText("+")
        focus_in_button.clicked.connect(lambda: self.nudge("in"))

        focus_out_button = QtWidgets.QToolButton()
        focus_out_button.setText("-")
        focus_out_button.clicked.connect(lambda: self.nudge("out"))

        widget_label = QtWidgets.QLabel("Sample controls")
        layout = QtWidgets.QGridLayout()

        nudge_buttons.addWidget(
            self.nudge_amount_spin_box, 1, 1, QtCore.Qt.AlignmentFlag.AlignCenter
        )
        nudge_buttons.addWidget(up_button, 0, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        nudge_buttons.addWidget(down_button, 2, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        nudge_buttons.addWidget(left_button, 1, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        nudge_buttons.addWidget(right_button, 1, 2, QtCore.Qt.AlignmentFlag.AlignCenter)

        nudge_buttons.addWidget(
            focus_in_button, 0, 3, QtCore.Qt.AlignmentFlag.AlignCenter
        )
        nudge_buttons.addWidget(
            focus_out_button, 2, 3, QtCore.Qt.AlignmentFlag.AlignCenter
        )

        x_label = QtWidgets.QLabel("X Pos:")
        self.x_rb_label = QtWidgets.QLabel("0")
        self.x_val_input = QtWidgets.QLineEdit()
        self.x_val_input.setMinimumWidth(200)
        y_label = QtWidgets.QLabel("Y Pos:")
        self.y_rb_label = QtWidgets.QLabel("0")
        self.y_val_input = QtWidgets.QLineEdit()
        z_label = QtWidgets.QLabel("Z Pos:")
        self.z_rb_label = QtWidgets.QLabel("0")
        self.z_val_input = QtWidgets.QLineEdit()
        nudge_buttons.addWidget(x_label, 0, 4)
        nudge_buttons.addWidget(self.x_rb_label, 0, 5)
        nudge_buttons.addWidget(self.x_val_input, 0, 6)
        nudge_buttons.addWidget(y_label, 1, 4)
        nudge_buttons.addWidget(self.y_rb_label, 1, 5)
        nudge_buttons.addWidget(self.y_val_input, 1, 6)
        nudge_buttons.addWidget(z_label, 2, 4)
        nudge_buttons.addWidget(self.z_rb_label, 2, 5)
        nudge_buttons.addWidget(self.z_val_input, 2, 6)

        self.x_val_input.returnPressed.connect(lambda: self.set_motor_position("x"))
        self.y_val_input.returnPressed.connect(lambda: self.set_motor_position("y"))
        self.z_val_input.returnPressed.connect(lambda: self.set_motor_position("z"))

        readback_values_layout = QtWidgets.QGridLayout()

        M.x.subscribe(lambda value, **kwargs: self.update_label("x", value))
        M.y.subscribe(lambda value, **kwargs: self.update_label("y", value))
        M.z.subscribe(lambda value, **kwargs: self.update_label("z", value))

        self.position_save_text_box = QtWidgets.QLineEdit()
        self.position_save_button = QtWidgets.QPushButton("Save Position")

        readback_values_layout.addWidget(self.position_save_text_box, 3, 0)
        readback_values_layout.addWidget(self.position_save_button, 3, 1)

        self.saved_positions_list = SamplePositionQueueWidget()
        self.position_save_button.clicked.connect(self.save_motor_positions)
        self.saved_positions_list.go_to_position_signal.connect(
            self.set_motor_positions
        )
        readback_values_layout.addWidget(self.saved_positions_list, 5, 0, 1, 2)

        layout.addWidget(widget_label, 0, 0)
        layout.addLayout(nudge_buttons, 1, 0)
        layout.addLayout(readback_values_layout, 2, 0, 1, 2)

        self.setLayout(layout)

    def set_motor_position(self, pos):
        try:
            if pos == "x":
                M.x.user_setpoint.set(float(self.x_val_input.text()))
            elif pos == "y":
                M.y.user_setpoint.set(float(self.y_val_input.text()))
            elif pos == "z":
                M.z.user_setpoint.set(float(self.z_val_input.text()))
        except Exception as e:
            pass

    def set_motor_positions(self, data: Position):
        self.x_val_input.setText(str(data.x))
        self.y_val_input.setText(str(data.y))
        self.z_val_input.setText(str(data.z))
        self.set_motor_position("x")
        self.set_motor_position("y")
        self.set_motor_position("z")

    def save_motor_positions(self):
        self.saved_positions_list.add_item(
            self.position_save_text_box.text(),
            M.x.user_readback.get(),
            M.y.user_readback.get(),
            M.z.user_readback.get(),
        )

    def update_label(self, label_name, value):
        label_mapping = {
            "x": self.x_rb_label,
            "y": self.y_rb_label,
            "z": self.z_rb_label,
        }
        label_mapping[label_name].setText(f"{value:.3f}")

    def nudge(self, direction: str):
        direction_motors = {
            "up": (M.y, 1),
            "down": (M.y, -1),
            "left": (M.x, -1),
            "right": (M.x, 1),
            "in": (M.z, 1),
            "out": (M.z, -1),
        }
        motor, factor = direction_motors[direction]
        pbar_manager = RE.waiting_hook
        RE.waiting_hook = None
        RE(bps.mvr(motor, float(self.nudge_amount_spin_box.text()) * factor))
        RE.waiting_hook = pbar_manager

class ScanSetupWidget(QtWidgets.QGroupBox):
    add_to_queue_signal = QtCore.Signal(str, object)

    def __init__(self):
        super().__init__()
        self.widget_layout = QtWidgets.QGridLayout()
        self.setTitle("Scan Setup")
        # label = QtWidgets.QLabel("Scan Setup widget")
        # self.widget_layout.addWidget(label)
        self.setLayout(self.widget_layout)
        self.positions: list[QueueItem] = []
        self.setup_position_inputs()
        self.setup_other_inputs()
        self.setup_metadata_inputs()

    def setup_position_inputs(self):
        validator = QtGui.QDoubleValidator()
        self.start_x_input = QtWidgets.QLineEdit()
        self.start_x_input.setValidator(validator)
        self.start_y_input = QtWidgets.QLineEdit()
        self.start_y_input.setValidator(validator)
        self.stop_x_input = QtWidgets.QLineEdit()
        self.stop_x_input.setValidator(validator)
        self.stop_y_input = QtWidgets.QLineEdit()
        self.stop_y_input.setValidator(validator)

        self.start_presets_combobox = QtWidgets.QComboBox()
        self.end_presets_combobox = QtWidgets.QComboBox()
        self.start_presets_combobox.currentIndexChanged.connect(self.populate_start)
        self.end_presets_combobox.currentIndexChanged.connect(self.populate_end)

        start_label = QtWidgets.QLabel("Start")
        stop_label = QtWidgets.QLabel("Stop")
        x_label = QtWidgets.QLabel("X")
        y_label = QtWidgets.QLabel("Y")

        self.widget_layout.addWidget(start_label, 1, 0)
        self.widget_layout.addWidget(stop_label, 2, 0)
        self.widget_layout.addWidget(x_label, 0, 1)
        self.widget_layout.addWidget(y_label, 0, 2)

        self.widget_layout.addWidget(self.start_x_input, 1, 1)
        self.widget_layout.addWidget(self.start_y_input, 1, 2)
        self.widget_layout.addWidget(self.stop_x_input, 2, 1)
        self.widget_layout.addWidget(self.stop_y_input, 2, 2)
        self.widget_layout.addWidget(self.start_presets_combobox, 1, 3)
        self.widget_layout.addWidget(self.end_presets_combobox, 2, 3)

    def populate_start(self, idx):
        if self.positions:
            self.start_x_input.setText(str(self.positions[idx].data.x))
            self.start_y_input.setText(str(self.positions[idx].data.y))

    def populate_end(self, idx):
        if self.positions:
            self.stop_x_input.setText(str(self.positions[idx].data.x))
            self.stop_y_input.setText(str(self.positions[idx].data.y))

    def update_combo_boxes(self, positions: list[QueueItem]):
        self.positions = positions #[QueueItem("", Position(0, 0, 0))] + positions
        self.start_presets_combobox.clear()
        self.start_presets_combobox.addItems([pos.label for pos in self.positions])
        self.end_presets_combobox.clear()
        self.end_presets_combobox.addItems([pos.label for pos in self.positions])

    def setup_other_inputs(self):
        float_validator = QtGui.QDoubleValidator()
        self.estimated_time = QtWidgets.QLabel("0")
        self.step_size_input = QtWidgets.QLineEdit()

        self.step_size_input.setValidator(float_validator)
        self.dwell_input = QtWidgets.QLineEdit()

        self.dwell_input.setValidator(float_validator)

        self.widget_layout.addWidget(QtWidgets.QLabel("Step Size (mm): "), 3, 0)
        self.widget_layout.addWidget(self.step_size_input, 3, 1)
        self.widget_layout.addWidget(QtWidgets.QLabel("Dwell time (s): "), 4, 0)
        self.widget_layout.addWidget(self.dwell_input, 4, 1)

        self.scan_name_input = QtWidgets.QLineEdit()
        self.widget_layout.addWidget(QtWidgets.QLabel("Scan Name: "), 5, 0)
        self.widget_layout.addWidget(self.scan_name_input, 5, 1)

        self.widget_layout.addWidget(
            QtWidgets.QLabel("Est. Time (s): "), 6, 0
        )
        self.widget_layout.addWidget(self.estimated_time, 6, 1)

        self.add_to_queue_button = QtWidgets.QPushButton("Add to Queue")
        self.widget_layout.addWidget(self.add_to_queue_button, 9, 0)

        # Connect slots
        self.start_x_input.textChanged.connect(self.calculate_estimated_time)
        self.stop_x_input.textChanged.connect(self.calculate_estimated_time)
        self.start_y_input.textChanged.connect(self.calculate_estimated_time)
        self.stop_y_input.textChanged.connect(self.calculate_estimated_time)
        self.step_size_input.textChanged.connect(self.calculate_estimated_time)
        self.dwell_input.textChanged.connect(self.calculate_estimated_time)
        self.add_to_queue_button.clicked.connect(self.add_to_queue)

    def calculate_estimated_time(self, _):
        try:
            num_pixels_x = abs(
                float(self.stop_x_input.text()) - float(self.start_x_input.text())
            ) / float(self.step_size_input.text())
            num_pixels_y = abs(
                float(self.stop_y_input.text()) - float(self.start_y_input.text())
            ) / float(self.step_size_input.text())
            # Time in ms
            est_time = num_pixels_x * num_pixels_y * float(self.dwell_input.text())
            self.estimated_time.setText(str(est_time))
        except Exception as e:
            pass

    def setup_metadata_inputs(self):
        self.dynamic_widget_container = QtWidgets.QWidget()
        self.dynamic_layout = QtWidgets.QGridLayout(self.dynamic_widget_container)
        self.widget_layout.addWidget(self.dynamic_widget_container, 8, 0, 1, 2)
        self.metadata_type_combobox = QtWidgets.QComboBox()
        self.metadata_type_combobox.currentIndexChanged.connect(self.update_line_edits)
        self.metadata_type_combobox.addItems(["sample", "scan"])
        self.widget_layout.addWidget(QtWidgets.QLabel("Metadata type: "), 7, 0)
        self.widget_layout.addWidget(self.metadata_type_combobox, 7, 1)

    def update_line_edits(self):
        for i in reversed(range(self.dynamic_layout.count())):
            widget = self.dynamic_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        # Create new labels and QLineEdits based on the combo box selection
        option = self.metadata_type_combobox.currentText()
        if option == "sample":
            labels = [field.name for field in fields(SampleMetadata)]
        elif option == "scan":
            labels = [field.name for field in fields(ScanMetadata)]

        # Add new QLineEdits and labels
        for i, label_text in enumerate(labels):
            label = QtWidgets.QLabel(f"{label_text}")
            line_edit = QtWidgets.QLineEdit()
            self.dynamic_layout.addWidget(label, i, 0, 1, 1)
            self.dynamic_layout.addWidget(line_edit, i, 1, 1, 1)

    def fill_inputs_from_definition(self, data: MaiaFlyDefinition, index=None):
        self.start_x_input.setText(str(data.xstart))
        self.start_y_input.setText(str(data.ystart))
        self.stop_x_input.setText(str(data.xstop))
        self.stop_y_input.setText(str(data.ystop))
        self.step_size_input.setText(str(data.xpitch))
        self.dwell_input.setText(str(data.dwell))
        self.scan_name_input.setText(str(data.name))

        if isinstance(data.md, SampleMetadata):
            self.metadata_type_combobox.setCurrentText("sample")
            for i, field in enumerate(fields(data.md)):
                val = getattr(data.md, field.name)
                widget = self.dynamic_layout.itemAtPosition(i, 1).widget()
                widget.setText(str(val))

    def add_to_queue(self):
        md = SampleMetadata(
                    info=self.dynamic_layout.itemAtPosition(0, 1).widget().text(),
                    owner=self.dynamic_layout.itemAtPosition(1, 1).widget().text(),
                    serial=self.dynamic_layout.itemAtPosition(2, 1).widget().text(),
                    type=self.dynamic_layout.itemAtPosition(3, 1).widget().text(),
                )
        self.add_to_queue_signal.emit(
            self.scan_name_input.text(),
            MaiaFlyDefinition(
                **{
                    "ystart": float(self.start_y_input.text()),
                    "ystop": float(self.stop_y_input.text()),
                    "ypitch": float(self.step_size_input.text()),
                    "xstart": float(self.stop_x_input.text()),
                    "xstop": float(self.stop_y_input.text()),
                    "xpitch": float(self.step_size_input.text()),
                    "dwell": float(self.dwell_input.text()),
                    "md": md,
                }
            ),
        )


class MicroscopeViewWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.widget_layout = QtWidgets.QGridLayout()
        # label = QtWidgets.QLabel("Microscope View widget")
        # self.widget_layout.addWidget(label)
        self.setLayout(self.widget_layout)
        plugins = [CrossHairPlugin]
        self.microscope = Microscope(self, viewport=False, plugins=plugins)
        self.microscope.scale = [0, 400]
        self.microscope.fps = 30
        # self.microscope.url = "http://10.68.25.94/mjpg/1/video.mjpg"
        self.microscope.url = "http://10.68.25.92/mjpg/1/video.mjpg"
        self.widget_layout.addWidget(self.microscope, 0, 0)
        # self.microscope.acquire(True)


class DetectorImageWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.widget_layout = QtWidgets.QGridLayout()
        label = QtWidgets.QLabel("Detector Image widget")
        self.widget_layout.addWidget(label)
        self.setLayout(self.widget_layout)


class ScanControlWidget(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__()
        self.setLayout(QtWidgets.QGridLayout())
        self.queue_widget = CollectionQueueWidget()
        self.layout().addWidget(self.queue_widget, 0, 0)
        # self.re_controls = RunEngineControls(RE, self, motors=None)
        
        self._setup_shutter_button()
        self.setTitle("Scan Queue")

    def set_re_controls(self, re_controls):
        self.re_controls = re_controls
        self.layout().addWidget(self.re_controls.widget, 1, 0)

    def plan(self):
        yield from bps.sleep(1)
        yield from bps.sleep(1)
        yield from bps.sleep(1)
        yield from bps.sleep(1)

    def _setup_shutter_button(self):
        if shutter.status.get() == "Open":
            shutter_button_label = "Close Shutter"
        else:
            shutter_button_label = "Open Shutter"

        self.shutter_button = QtWidgets.QPushButton(shutter_button_label)
        self.shutter_button.clicked.connect(self.toggle_shutter)
        self.layout().addWidget(self.shutter_button, 2, 0)

    def toggle_shutter(self):
        if shutter.status.get() == "Open":
            # yield from bps.mv(shutter, "Close")
            shutter.set("Close")
            self.shutter_button.setText("Open Shutter")
        else:
            # yield from bps.mv(shutter, "Open")
            shutter.set("Open")
            self.shutter_button.setText("Close Shutter")


class MAIAGUI:
    def __init__(self):
        self.window = window = MAIAGUIMainWindow()
        self.run_engine_controls = RunEngineControls(
            RE, self.window.scan_control_widget
        )
        self.window.scan_control_widget.set_re_controls(self.run_engine_controls)

    def show(self):
        self.window.show()

    def close(self):
        self.window.close()


class MAIAGUIMainWindow(QtWidgets.QMainWindow):


    def __init__(self, parent=None, filter_obj=None) -> None:
        super(MAIAGUIMainWindow, self).__init__(parent)
        self.setWindowTitle("MAIA data acquisition")
        self.main_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.main_widget)
        self._create_menu_bar()
        self._create_layout()

    def show(self):
        super().show()
        self.microscope_view_widget.microscope.acquire(True)

    def closeEvent(self, event):
        self.microscope_view_widget.microscope.acquire(False)
        event.accept()

    def _create_menu_bar(self):
        menuBar = self.menuBar()
        # self.setMenuBar(menuBar)
        # Creating menus using a QMenu object
        fileMenu = QtWidgets.QMenu("&File", self)
        menuBar.addMenu(fileMenu)
        # Adding actions to the File menu
        openAction = QtWidgets.QAction("&Open Excel Plan", self)
        fileMenu.addAction(openAction)
        openAction.triggered.connect(self.import_excel_plan)

        exitAction = QtWidgets.QAction("&Exit", self)
        exitAction.triggered.connect(self.close)  # Connect to close the application
        fileMenu.addAction(exitAction)


    def _create_layout(self):
        self.widget_layout = QtWidgets.QGridLayout()
        self._add_widgets()
        self.main_widget.setLayout(self.widget_layout)

    def _add_widgets(self):
        # Adding import button
        self.scan_control_widget = ScanControlWidget()
        self.widget_layout.addWidget(self.scan_control_widget, 1, 0, 2, 1)

        self.sample_control_widget = SampleControlWidget()
        self.widget_layout.addWidget(self.sample_control_widget, 1, 1)

        self.microscope_view_widget = MicroscopeViewWidget()
        self.widget_layout.addWidget(self.microscope_view_widget, 1, 2)

        self.scan_setup_widget = ScanSetupWidget()
        self.widget_layout.addWidget(self.scan_setup_widget, 2, 1)

        self.detector_image_widget = DetectorImageWidget()
        self.widget_layout.addWidget(self.detector_image_widget, 2, 2)

        # Wiring up signals
        self.sample_control_widget.saved_positions_list.queue_updated.connect(
            self.scan_setup_widget.update_combo_boxes
        )
        self.scan_setup_widget.add_to_queue_signal.connect(
            self.scan_control_widget.queue_widget.add_item
        )
        self.scan_control_widget.queue_widget.selected_item_data_signal.connect(
            self.scan_setup_widget.fill_inputs_from_definition
        )


    def import_excel_plan(self):
        dialog = QtWidgets.QFileDialog()
        filename, _ = dialog.getOpenFileName(
            self, "Import Plan", filter="Excel (*.xlsx), csv (*.csv)"
        )
        df = None
        if filename.endswith(".xlsx"):
            df = pd.read_excel(filename)
        elif filename.endswith(".csv"):
            df = pd.read_csv(filename)

        if df is not None:
            df.columns = df.columns.str.lower()
            expected_columns = [
                "name",
                "serial",
                "info",
                "xstart",
                "xstop",
                "ystart",
                "ystop",
                "pitch",
                "dwell",
                "type",
                "owner",
            ]

            missing_columns = set(expected_columns) - set(df.columns)
            if missing_columns:
                self.show_error_dialog(
                    f"Columns missing from imported excel: {','.join(list(missing_columns))}"
                )
                return
            for i, row in df.iterrows():
                md = SampleMetadata(
                    info=str(row["info"]),
                    owner=str("owner"),
                    serial=str(row["serial"]),
                    type=str(row["type"]),
                )
                collection_data = MaiaFlyDefinition(
                    ystart=row["ystart"],
                    ystop=row["ystop"],
                    ypitch=row["pitch"],
                    xstart=row["xstart"],
                    xstop=row["xstop"],
                    xpitch=row["pitch"],
                    dwell=row["dwell"],
                    name=str(row["name"]),
                    md=md,
                )
                self.scan_control_widget.queue_widget.add_item(
                    row["name"], collection_data
                )

    def show_error_dialog(self, message):
        dlg = QtWidgets.QMessageBox(self)
        dlg.setWindowTitle("Error")
        dlg.setText(message)
        dlg.exec()


_create_qApp()

try:
    maia_gui.close()
except NameError:
    pass

maia_gui = MAIAGUI()
