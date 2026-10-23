from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Optional
from collections import defaultdict
from pathlib import Path
import json
import requests

import bluesky.plan_stubs as bps
import pandas as pd
from bluesky.utils import RunEngineInterrupted

# install_qt_kicker()
from qtpy import QtCore, QtGui, QtWidgets
# from matplotlib.backends.qt_compat import QtCore, QtGui, QtWidgets
# from matplotlib.backends.backend_qt5 import _create_qApp
import qtpy
# if qtpy.PYSIDE6:
#    from PySide6 import QtCore, QtWidgets, QtGui


from qmicroscope.microscope import Microscope
from qmicroscope.plugins import CrossHairPlugin

resp = requests.get("https://api.nsls2.bnl.gov/v1/facility/nsls2/cycles/current") 
current_cycle = resp.json()["cycle"]

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
    maia_scan_number: "Optional[int]" = None
    bluesky_run_id: "Optional[UUID]" = None
    path: str = ""


class RequestStatus(Enum):
    # Colors are tuple of values for (foreground, background)
    COLLECTING = (QtCore.Qt.GlobalColor.black, QtCore.Qt.GlobalColor.green) 
    COMPLETE = (QtCore.Qt.GlobalColor.black, QtCore.Qt.GlobalColor.gray)
    QUEUED = (QtCore.Qt.GlobalColor.black, QtCore.Qt.GlobalColor.white)


class QueueItem:
    def __init__(self, label, data):
        self.label = label
        self.data = data
        self.status = RequestStatus.QUEUED


class QueueModel:
    def __init__(self, queue=None, update_duplicate_item=True):
        if queue is None:
            self.queue: list[QueueItem] = []
        else:
            self.queue: list[QueueItem] = queue
        
        self.update_duplicate_item = update_duplicate_item

    def add_item(self, item):
        item_added = False
        # Check if item label is empty
        if not item.label:
            raise ValueError("No label specified for item")
        # Check if new item has the same label as existing item
        matches = 1
        for i in self.queue:
            if i.label == item.label:
                if self.update_duplicate_item:
                    i.data = item.data
                    item_added = True 
                # raise ValueError(f"Item with label {item.label} already exists")
                else:
                    item.label = item.label.split("__")[0] + f"__{matches}"
                    matches += 1


        if not item_added:
            self.queue.append(item)

    def remove_item(self, index):
        if 0 <= index < len(self.queue):
            del self.queue[index]

    def remove_all_items(self):
        self.queue = []


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

    def __init__(self, update_duplicate_item=True):
        super().__init__()
        self.model = QueueModel(queue=self.load_list(), update_duplicate_item=update_duplicate_item)
        self.init_ui()
        self.update_list()

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

        self.remove_all_items_button = QtWidgets.QPushButton("Remove ALL Items")
        self.remove_all_items_button.clicked.connect(self.remove_all_items)
        self.layout().addWidget(self.remove_all_items_button)

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

    def remove_all_items(self):
        reply = QtWidgets.QMessageBox.question(
                self,
                "Remove all items",
                "This will remove all items from list, Are you sure?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
                )
        if reply == QtWidgets.QMessageBox.Yes:
            self.model.remove_all_items()
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

    def dump_list(self):
        pass

    def load_list(self):
        return []

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
        self.dump_list()
        self.queue_updated.emit(self.model.get_items())


class SamplePositionQueueWidget(QueueWidget):
    go_to_position_signal = QtCore.Signal(object)
    item_selected = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self.list_widget.selectionModel().selectionChanged.connect(self.on_selection_changed)

    def on_selection_changed(self, selected, deselected):
        selected_indexes = self.list_widget.selectedIndexes()
        if selected_indexes:
            last_selected = selected_indexes[-1]
            item = self.model.get_items()[last_selected.row()]
            self.item_selected.emit(item)

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

    def dump_list(self):
        pos_list = []
        for pos_item in self.model.get_items():
            pos_list.append({"label": pos_item.label, "data": [pos_item.data.x, pos_item.data.y, pos_item.data.z]})
        with open("position_queue.json", "w", encoding="utf-8") as f:
            json.dump(pos_list, f, indent=2)

    def load_list(self):
        path = Path("position_queue.json")
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return [QueueItem(label=d["label"], data=Position(d["data"][0], d["data"][1], d["data"][2])) for d in payload]

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

    def item_to_dict(self, item: QueueItem):
        return {
                "label": item.label,
                "data": asdict(item.data),
                "status": item.status.name
                }

    def item_from_dict(self, d: dict):
        item = QueueItem(label=d["label"], data = MaiaFlyDefinition(**d["data"]))
        item.status = RequestStatus[d["status"]]
        return item

    def dump_list(self):
        serialized_list = [self.item_to_dict(item) for item in self.model.get_items()]
        with open("request_queue.json", "w", encoding="utf-8") as f:
            json.dump(serialized_list, f, indent=2)

    def load_list(self):
        path = Path("request_queue.json")
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return [self.item_from_dict(d) for d in payload]

class RunEngineState(str, Enum):
    idle = "idle"
    running = "running"
    paused = "paused"


def maia_plan(payload):
    def main_plan(payload):
        md = payload.md if isinstance(payload.md, dict) else asdict(payload.md)
        yield from fly_maia(
                ystart=payload.ystart,
                ystop=payload.ystop,
                ypitch=payload.ypitch,
                xstart=payload.xstart,
                xstop=payload.xstop,
                xpitch=payload.xpitch,
                dwell=payload.dwell,
                md=md,
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
        widget_layout = QtWidgets.QGridLayout()
        button_layout = QtWidgets.QHBoxLayout()
        button_widget.setLayout(widget_layout)

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

        widget_layout.addLayout(button_layout, 6, 0, 2, 2)

        # Proposal number
        self.proposal_number_label = QtWidgets.QLabel("Proposal number:")
        self.proposal_number_edit = QtWidgets.QLineEdit()
        self.proposal_number_edit.setValidator(QtGui.QIntValidator())
        widget_layout.addWidget(self.proposal_number_label, 1, 0)
        widget_layout.addWidget(self.proposal_number_edit, 1, 1)

        # MAIA Scan number
        self.maia_scan_number_label = QtWidgets.QLabel("MAIA scan number:")
        self.maia_scan_number_edit = QtWidgets.QLineEdit()
        self.maia_scan_number_edit.setValidator(QtGui.QIntValidator())
        widget_layout.addWidget(self.maia_scan_number_label, 2, 0)
        widget_layout.addWidget(self.maia_scan_number_edit, 2, 1)

        # Path to store run summary
        self.run_summary_label = QtWidgets.QLabel("Run summary path:")
        self.run_summary_path_edit = QtWidgets.QLineEdit()
        widget_layout.addWidget(self.run_summary_label, 3, 0)
        widget_layout.addWidget(self.run_summary_path_edit, 4, 0, 1, 2)

        # Generate report
        self.generate_report_button = QtWidgets.QPushButton("Generate report")
        self.generate_report_button.clicked.connect(self.write_run_summary_to_file)
        widget_layout.addWidget(self.generate_report_button, 5, 1)


        self.RE.state_hook = self.handle_state_change
        self.handle_state_change(self.RE.state, None)
        self.current_request = None


    def set_queue_widget_model(self, model):
        self.queue_widget_model: QueueModel = model


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
                    if self.maia_scan_number_edit.text():
                        self.maia_scan_number_edit.setText(str(int(self.maia_scan_number_edit.text()) + 1))
                        item.data.maia_scan_number = int(self.maia_scan_number_edit.text())
                        item.data.path = f"/nsls2/data/xfm/proposals/{current_cycle}/pass-{self.proposal_number_edit.text()}/assets/384B4/{item.data.md.type}/{self.maia_scan_number_edit.text()}"
                    self.GUI.queue_widget.set_status(item, RequestStatus.COLLECTING)
                    item.data.bluesky_run_id, = self.RE(
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

    def write_run_summary_to_file(self):
        dialog = QtWidgets.QFileDialog(caption="Save excel file")
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dialog.setNameFilter("Excel files (*.xlsx)")
        dialog.setDefaultSuffix("xlsx")
        dialog.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
        if dialog.exec_():
            fname = dialog.selectedFiles()[0]
            data = defaultdict(list)
            for item in self.queue_widget_model.get_items():
                if item.status is not RequestStatus.QUEUED:
                    data["Sample name"].append(item.data.name)
                    data["Type"].append(item.data.md.type)
                    data["Info"].append(item.data.md.info)
                    data["Serial #"].append(item.data.md.serial)
                    data["Dwell time (ms)"].append(item.data.dwell)
                    data["Step size (um)"].append(item.data.xpitch)
                    data["Path"].append(item.data.path)
                    data["Owner"].append(item.data.md.owner)
                    data["MAIA scan number"].append(item.data.maia_scan_number)
                    data["Bluesky RUN ID"].append(item.data.bluesky_run_id)
            df = pd.DataFrame(data)
            df.to_excel(fname, index=False)


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
        self.setTitle("Sample Control (mm)")
        nudge_buttons = QtWidgets.QGridLayout()
        # nudge_buttons.addWidget(label)
        self.nudge_amount_spin_box = QtWidgets.QDoubleSpinBox()
        self.nudge_amount_spin_box.setDecimals(3)
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

        position_label = QtWidgets.QLabel("Position")
        current_value_label = QtWidgets.QLabel("Current Value")
        setpoint_value_label = QtWidgets.QLabel("Setpoint Value")
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.VLine)
        line2 = QtWidgets.QFrame()
        line2.setFrameShape(QtWidgets.QFrame.VLine)
        x_label = QtWidgets.QLabel("X")
        x_label.setAlignment(QtCore.Qt.AlignCenter)
        self.x_rb_label = QtWidgets.QLabel("0")
        self.x_rb_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.x_val_input = QtWidgets.QLineEdit()
        y_label = QtWidgets.QLabel("Y")
        y_label.setAlignment(QtCore.Qt.AlignCenter)
        self.y_rb_label = QtWidgets.QLabel("0")
        self.y_rb_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.y_val_input = QtWidgets.QLineEdit()
        z_label = QtWidgets.QLabel("Z")
        z_label.setAlignment(QtCore.Qt.AlignCenter)
        self.z_rb_label = QtWidgets.QLabel("0")
        self.z_rb_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.z_val_input = QtWidgets.QLineEdit()

        nudge_buttons.addWidget(line, 0, 5, 4, 1)
        nudge_buttons.addWidget(line2, 0, 7, 4, 1)
        nudge_buttons.addWidget(position_label, 0, 4)
        nudge_buttons.addWidget(current_value_label, 0, 6)
        nudge_buttons.addWidget(setpoint_value_label, 0, 8)
        nudge_buttons.addWidget(x_label, 1, 4)
        nudge_buttons.addWidget(self.x_rb_label, 1, 6)
        nudge_buttons.addWidget(self.x_val_input, 1, 8)
        nudge_buttons.addWidget(y_label, 2, 4)
        nudge_buttons.addWidget(self.y_rb_label, 2, 6)
        nudge_buttons.addWidget(self.y_val_input, 2, 8)
        nudge_buttons.addWidget(z_label, 3, 4)
        nudge_buttons.addWidget(self.z_rb_label, 3, 6)
        nudge_buttons.addWidget(self.z_val_input, 3, 8)

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
        self.position_save_text_box.returnPressed.connect(self.save_motor_positions)
        self.position_save_button.clicked.connect(self.save_motor_positions)
        self.saved_positions_list.go_to_position_signal.connect(
            self.set_motor_positions
        )
        self.saved_positions_list.item_selected.connect(self.populate_data)
        readback_values_layout.addWidget(self.saved_positions_list, 5, 0, 1, 2)

        layout.addWidget(widget_label, 0, 0)
        layout.addLayout(nudge_buttons, 1, 0)
        layout.addLayout(readback_values_layout, 2, 0, 1, 2)

        self.setLayout(layout)

    def populate_data(self, item: QueueItem):
        self.position_save_text_box.setText(item.label)
        self.x_val_input.setText(str(item.data.x))
        self.y_val_input.setText(str(item.data.y))
        self.z_val_input.setText(str(item.data.z))

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

class BeamControlWidget(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__()
        self.widget_layout = QtWidgets.QGridLayout()
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.VLine)
        line2 = QtWidgets.QFrame()
        line2.setFrameShape(QtWidgets.QFrame.VLine)
        
        self.setTitle("Beam Control")

        device_label = QtWidgets.QLabel("Device")
        current_value_label = QtWidgets.QLabel("Current Value")
        setpoint_value_label = QtWidgets.QLabel("Setpoint Value")

        kb_hor_label = QtWidgets.QLabel("KB horizontal aperture")
        self.kb_hor_rb_label = QtWidgets.QLabel("0")
        self.kb_hor_input = QtWidgets.QLineEdit()
        self.kb_hor_input.setMinimumWidth(200)
        self.kb_hor_input.setMaximumWidth(300)

        kb_ver_label = QtWidgets.QLabel("KB vertical aperture")
        self.kb_ver_rb_label = QtWidgets.QLabel("0")
        self.kb_ver_input = QtWidgets.QLineEdit()
        self.kb_ver_input.setMinimumWidth(200)
        self.kb_ver_input.setMaximumWidth(250)

        ssa_hor_label = QtWidgets.QLabel("SSA horizontal aperture")
        self.ssa_hor_rb_label = QtWidgets.QLabel("0")
        self.ssa_hor_input = QtWidgets.QLineEdit()
        self.ssa_hor_input.setMinimumWidth(200)
        self.ssa_hor_input.setMaximumWidth(250)

        ssa_ver_label = QtWidgets.QLabel("SSA vertical aperture")
        self.ssa_ver_rb_label = QtWidgets.QLabel("0")
        self.ssa_ver_input = QtWidgets.QLineEdit()
        self.ssa_ver_input.setMinimumWidth(200)
        self.ssa_ver_input.setMaximumWidth(250)

        beam_control_layout = QtWidgets.QGridLayout()

        beam_control_layout.addWidget(line, 0, 1, 5, 1)
        beam_control_layout.addWidget(line2, 0, 3, 5, 1)

        beam_control_layout.addWidget(device_label, 0, 0)
        beam_control_layout.addWidget(current_value_label, 0, 2)
        beam_control_layout.addWidget(setpoint_value_label, 0, 4)

        beam_control_layout.addWidget(kb_hor_label, 1, 0)
        beam_control_layout.addWidget(self.kb_hor_rb_label, 1, 2)
        beam_control_layout.addWidget(self.kb_hor_input, 1, 4)

        beam_control_layout.addWidget(kb_ver_label, 2, 0)
        beam_control_layout.addWidget(self.kb_ver_rb_label, 2, 2)
        beam_control_layout.addWidget(self.kb_ver_input, 2, 4)

        beam_control_layout.addWidget(ssa_hor_label, 3, 0)
        beam_control_layout.addWidget(self.ssa_hor_rb_label, 3, 2)
        beam_control_layout.addWidget(self.ssa_hor_input, 3, 4)  

        beam_control_layout.addWidget(ssa_ver_label, 4, 0)
        beam_control_layout.addWidget(self.ssa_ver_rb_label, 4, 2)
        beam_control_layout.addWidget(self.ssa_ver_input, 4, 4)

        self.setLayout(beam_control_layout)

        self.kb_hor_input.returnPressed.connect(lambda: self.set_motor_position("kb_hor"))
        self.kb_ver_input.returnPressed.connect(lambda: self.set_motor_position("kb_ver"))
        self.ssa_hor_input.returnPressed.connect(lambda: self.set_motor_position("ssa_hor"))
        self.ssa_ver_input.returnPressed.connect(lambda: self.set_motor_position("ssa_ver"))

        kb_slits.horizontal.subscribe(lambda value, **kwargs: self.update_label("kb_hor", value))
        kb_slits.vertical.subscribe(lambda value, **kwargs: self.update_label("kb_ver", value))

        ssa_slits.horizontal.subscribe(lambda value, **kwargs: self.update_label("ssa_hor", value))
        ssa_slits.vertical.subscribe(lambda value, **kwargs: self.update_label("ssa_ver", value))

    
    def update_label(self, label_name, value):
        label_mapping = {
            "kb_hor": self.kb_hor_rb_label,
            "kb_ver": self.kb_ver_rb_label,
            "ssa_hor": self.ssa_hor_rb_label,
            "ssa_ver": self.ssa_ver_rb_label
        }
        label_mapping[label_name].setText(f"{value:.3f}")      
    
    
    def set_motor_position(self, pos):
        try:
            if pos == "kb_hor":
                kb_slits.horizontal.user_setpoint.set(float(self.kb_hor_input.text()))
            elif pos == "kb_ver":
                kb_slits.vertical.user_setpoint.set(float(self.kb_ver_input.text()))
            elif pos == "ssa_hor":
                ssa_slits.horizontal.user_setpoint.set(float(self.ssa_hor_input.text()))
            elif pos == "ssa_ver":
                ssa_slits.vertical.user_setpoint.set(float(self.ssa_ver_input.text()))
        except Exception as e:
            pass

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
        self.xstart_input = QtWidgets.QLineEdit()
        self.xstart_input.setValidator(validator)
        self.ystart_input = QtWidgets.QLineEdit()
        self.ystart_input.setValidator(validator)
        self.xstop_input = QtWidgets.QLineEdit()
        self.xstop_input.setValidator(validator)
        self.ystop_input = QtWidgets.QLineEdit()
        self.ystop_input.setValidator(validator)

        self.start_presets_combobox = QtWidgets.QComboBox()
        self.end_presets_combobox = QtWidgets.QComboBox()
        self.start_presets_combobox.currentIndexChanged.connect(self.populate_start)
        self.end_presets_combobox.currentIndexChanged.connect(self.populate_end)

        start_label = QtWidgets.QLabel("Start")
        stop_label = QtWidgets.QLabel("Stop")
        x_label = QtWidgets.QLabel("X")
        y_label = QtWidgets.QLabel("Y")
        saved_position_label = QtWidgets.QLabel("Saved positions")
        
        self.widget_layout.addWidget(x_label, 1, 0)
        self.widget_layout.addWidget(y_label, 2, 0)
        self.widget_layout.addWidget(start_label, 0, 1)
        self.widget_layout.addWidget(stop_label, 0, 2)
        self.widget_layout.addWidget(saved_position_label, 3, 0)

        self.widget_layout.addWidget(self.xstart_input, 1, 1)
        self.widget_layout.addWidget(self.ystart_input, 2, 1)
        self.widget_layout.addWidget(self.xstop_input, 1, 2)
        self.widget_layout.addWidget(self.ystop_input, 2, 2)

        self.widget_layout.addWidget(self.start_presets_combobox, 3, 1)
        self.widget_layout.addWidget(self.end_presets_combobox, 3, 2)

    def populate_start(self, idx):
        if self.positions:
            self.xstart_input.setText(str(self.positions[idx].data.x))
            self.ystart_input.setText(str(self.positions[idx].data.y))

    def populate_end(self, idx):
        if self.positions:
            self.xstop_input.setText(str(self.positions[idx].data.x))
            self.ystop_input.setText(str(self.positions[idx].data.y))

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

        self.widget_layout.addWidget(QtWidgets.QLabel("Step Size (mm): "), 4, 0)
        self.widget_layout.addWidget(self.step_size_input, 4, 1)
        self.widget_layout.addWidget(QtWidgets.QLabel("Dwell time (s): "), 5, 0)
        self.widget_layout.addWidget(self.dwell_input, 5, 1)

        self.scan_name_input = QtWidgets.QLineEdit()
        self.widget_layout.addWidget(QtWidgets.QLabel("Scan Name: "), 6, 0)
        self.widget_layout.addWidget(self.scan_name_input, 6, 1)

        self.widget_layout.addWidget(
            QtWidgets.QLabel("Est. Time (s): "), 7, 0
        )
        self.widget_layout.addWidget(self.estimated_time, 7, 1)

        self.add_to_queue_button = QtWidgets.QPushButton("Add to Queue")
        self.widget_layout.addWidget(self.add_to_queue_button, 10, 0)

        # Connect slots
        self.xstart_input.textChanged.connect(self.calculate_estimated_time)
        self.xstop_input.textChanged.connect(self.calculate_estimated_time)
        self.ystart_input.textChanged.connect(self.calculate_estimated_time)
        self.ystop_input.textChanged.connect(self.calculate_estimated_time)
        self.step_size_input.textChanged.connect(self.calculate_estimated_time)
        self.dwell_input.textChanged.connect(self.calculate_estimated_time)
        self.add_to_queue_button.clicked.connect(self.add_to_queue)

    def calculate_estimated_time(self, _):
        try:
            num_pixels_x = abs(
                float(self.xstop_input.text()) - float(self.xstart_input.text())
            ) / float(self.step_size_input.text())
            num_pixels_y = abs(
                float(self.ystop_input.text()) - float(self.ystart_input.text())
            ) / float(self.step_size_input.text())
            # Time in ms
            seconds = num_pixels_x * num_pixels_y * float(self.dwell_input.text())
            hours = int(seconds // 3600)
            mins = int(seconds % 3600 // 60)
            seconds = int(seconds % 60)
            time_string = f"{hours:02}:{mins:02}:{seconds:02}"
            self.estimated_time.setText(time_string)
        except Exception as e:
            pass

    def setup_metadata_inputs(self):
        self.dynamic_widget_container = QtWidgets.QWidget()
        self.dynamic_layout = QtWidgets.QGridLayout(self.dynamic_widget_container)
        self.widget_layout.addWidget(self.dynamic_widget_container, 9, 0, 1, 2)
        self.widget_layout.addWidget(QtWidgets.QLabel("Metadata"), 8, 0)
        self.update_line_edits()

    def update_line_edits(self):

        # Create new labels and QLineEdits based on the combo box selection
        labels = [field.name for field in fields(SampleMetadata)]
        # Add new QLineEdits and labels
        for i, label_text in enumerate(labels):
            label = QtWidgets.QLabel(f"{label_text}")
            self.dynamic_layout.addWidget(label, i, 0, 1, 1)
            if label_text == "type":
                combo_box = QtWidgets.QComboBox()
                combo_box.addItems(["standard", "user"])
                self.dynamic_layout.addWidget(combo_box, i, 1, 1, 1)
            else:
                line_edit = QtWidgets.QLineEdit()
                self.dynamic_layout.addWidget(line_edit, i, 1, 1, 1)

    def fill_inputs_from_definition(self, data: MaiaFlyDefinition, index=None):
        self.xstart_input.setText(str(data.xstart))
        self.ystart_input.setText(str(data.ystart))
        self.xstop_input.setText(str(data.xstop))
        self.ystop_input.setText(str(data.ystop))
        self.step_size_input.setText(str(data.xpitch))
        self.dwell_input.setText(str(data.dwell))
        self.scan_name_input.setText(str(data.name))

        if isinstance(data.md, SampleMetadata):
            for i, field in enumerate(fields(data.md)):
                val = getattr(data.md, field.name)
                widget = self.dynamic_layout.itemAtPosition(i, 1).widget()
                widget.setText(str(val))

    def add_to_queue(self):
        md = SampleMetadata(
                    info=self.dynamic_layout.itemAtPosition(0, 1).widget().text(),
                    owner=self.dynamic_layout.itemAtPosition(1, 1).widget().text(),
                    serial=self.dynamic_layout.itemAtPosition(2, 1).widget().text(),
                    type=self.dynamic_layout.itemAtPosition(3, 1).widget().currentText(),
                )
        self.add_to_queue_signal.emit(
            self.scan_name_input.text(),
            MaiaFlyDefinition(
                **{
                    "ystart": float(self.ystart_input.text()),
                    "ystop": float(self.ystop_input.text()),
                    "ypitch": float(self.step_size_input.text()),
                    "xstart": float(self.xstart_input.text()),
                    "xstop": float(self.xstop_input.text()),
                    "xpitch": float(self.step_size_input.text()),
                    "dwell": float(self.dwell_input.text()),
                    "name": str(self.scan_name_input.text()),
                    "md": md,
                }
            ),
        )


class MicroscopeViewWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.widget_layout = QtWidgets.QGridLayout()
        self.setLayout(self.widget_layout)
        plugins = [CrossHairPlugin]
        self.microscope = Microscope(self, viewport=False, plugins=plugins)
        self.microscope.scale = [0, 400]
        self.microscope.fps = 30
        self.microscope.url = "http://10.68.25.92/mjpg/1/video.mjpg"
        self.widget_layout.addWidget(self.microscope, 0, 0)


class DetectorImageWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.widget_layout = QtWidgets.QGridLayout()
        self.setLayout(self.widget_layout)
        plugins = [CrossHairPlugin]
        self.microscope = Microscope(self, viewport=False, plugins=plugins)
        self.microscope.scale = [0, 400]
        self.microscope.fps = 30
        self.microscope.url = "http://10.68.25.94/mjpg/1/video.mjpg"
        self.widget_layout.addWidget(self.microscope, 0, 0)


class ScanControlWidget(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__()
        self.setLayout(QtWidgets.QGridLayout())
        self.queue_widget = CollectionQueueWidget(update_duplicate_item=False)
        self.layout().addWidget(self.queue_widget, 0, 0)
        # self.re_controls = RunEngineControls(RE, self, motors=None)
        
        self._setup_shutter_button()
        self.setTitle("Scan Queue")

    def set_re_controls(self, re_controls):
        self.re_controls: RunEngineControls = re_controls
        self.re_controls.set_queue_widget_model(self.queue_widget.model)
        self.layout().addWidget(self.re_controls.widget, 1, 0)

    def plan(self):
        yield from bps.sleep(1)
        yield from bps.sleep(1)
        yield from bps.sleep(1)
        yield from bps.sleep(1)

    def _setup_shutter_button(self):
        self.shutter_button = QtWidgets.QPushButton("")
        self.shutter_button.clicked.connect(self.toggle_shutter)
        if shutter.status.get() == "Open":
            shutter_button_label = "Close Shutter"
            self.shutter_button.setStyleSheet("background-color: red")
        else:
            shutter_button_label = "Open Shutter"
            self.shutter_button.setStyleSheet("background-color: green")
        self.shutter_button.setText(shutter_button_label)
        self.layout().addWidget(self.shutter_button, 2, 0)

    def toggle_shutter(self):
        if shutter.status.get() == "Open":
            shutter.set("Close")
            self.shutter_button.setText("Open Shutter")
            self.shutter_button.setStyleSheet("background-color: green")
        else:
            shutter.set("Open")
            self.shutter_button.setText("Close Shutter")
            self.shutter_button.setStyleSheet("background-color: red")


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
        openAction = QtGui.QAction("&Open Excel Plan", self)
        fileMenu.addAction(openAction)
        openAction.triggered.connect(self.import_excel_plan)

        exitAction = QtGui.QAction("&Exit", self)
        exitAction.triggered.connect(self.close)  # Connect to close the application
        fileMenu.addAction(exitAction)


    def _create_layout(self):
        self.widget_layout = QtWidgets.QGridLayout()
        self._add_widgets()
        self.main_widget.setLayout(self.widget_layout)

    def _add_widgets(self):
        # Adding import button
        self.scan_control_widget = ScanControlWidget()
        self.widget_layout.addWidget(self.scan_control_widget, 1, 0, 3, 1)

        self.sample_control_widget = SampleControlWidget()
        self.widget_layout.addWidget(self.sample_control_widget, 1, 1)

        self.microscope_view_widget = MicroscopeViewWidget()
        self.widget_layout.addWidget(self.microscope_view_widget, 1, 2)

        self.scan_setup_widget = ScanSetupWidget()
        self.widget_layout.addWidget(self.scan_setup_widget, 2, 1)

        self.beam_control_widget = BeamControlWidget()
        self.widget_layout.addWidget(self.beam_control_widget, 3, 1)

        self.detector_image_widget = DetectorImageWidget()
        self.widget_layout.addWidget(self.detector_image_widget, 2, 2)

        # Wiring up signals
        self.sample_control_widget.saved_positions_list.queue_updated.connect(
            self.scan_setup_widget.update_combo_boxes
        )
        self.sample_control_widget.saved_positions_list.update_list()
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


# _create_qApp()
qapp = QtWidgets.QApplication.instance()
if qapp is None:
    qapp = QtWidgets.QApplication([])

try:
    maia_gui.close()
except NameError:
    pass

maia_gui = MAIAGUI()
