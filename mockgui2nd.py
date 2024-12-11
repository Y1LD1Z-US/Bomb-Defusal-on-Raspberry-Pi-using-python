import sys
import random
from threading import Thread
from time import sleep
import traceback

# PyQt6 imports
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
    QProgressBar,
    QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

# Additional libraries
from pynput import keyboard
from digitalio import DigitalInOut, Direction, Pull
# import board
from adafruit_ht16k33.segments import Seg7x4
from adafruit_matrixkeypad import Matrix_Keypad

# Constants
COUNTDOWN = 300
PENALTY_TIME = 30  # Time penalty for wrong answers


# """
class MockPin:
    def __init__(self, initial_value=False):
        self._value = initial_value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, val):
        self._value = val

    def toggle(self):
        self._value = not self._value

    # Mimic DigitalInOut interface
    direction = None
    pull = None


class MockSeg7x4:
    def __init__(self):
        self.text = ""
        self.brightness = 0.5

    def print(self, text):
        self.text = text
        print(f"Display: {text}")


class MockMatrixKeypad:
    def __init__(self, rows, cols, keys):
        self.rows = rows
        self.cols = cols
        self.keys = keys
        self.flat_keys = [key for row in keys for key in row]
        self.pressed_keys = []

    def simulate_key_press(self, key):
        if key in self.flat_keys:
            self.pressed_keys = [key]
            print(f"Simulated Keypad Press: {key}")

    def clear_keys(self):
        self.pressed_keys = []
# """

class InputDisplay(QWidget):
    def __init__(
        self,
        num_pins,
        size=50,
        font_size=24,
        border_color_active="#00FF00",
        border_color_inactive="#FF0000",
        parent=None,
    ):
        """
        A customizable display for binary input pins.

        Args:
            num_pins (int): Number of input pins to display.
            size (int): Size of the circular labels (width and height).
            font_size (int): Font size for the labels.
            border_color_active (str): Border color when the pin is active (1).
            border_color_inactive (str): Border color when the pin is inactive (0).
            parent (QWidget): Parent widget.
        """
        super().__init__(parent)
        self.num_pins = num_pins
        self.size = size
        self.font_size = font_size
        self.border_color_active = border_color_active
        self.border_color_inactive = border_color_inactive
        self.input_labels = []

        # Create horizontal layout for circles
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        self.setLayout(layout)

        # Create individual circular labels for each pin
        for _ in range(num_pins):
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(self._get_stylesheet(active=False))
            layout.addWidget(label)
            self.input_labels.append(label)

        layout.addStretch()

    def _get_stylesheet(self, active):
        """
        Generate the stylesheet for the label.

        Args:
            active (bool): Whether the pin is active (True) or inactive (False).

        Returns:
            str: Stylesheet string.
        """
        border_color = (
            self.border_color_active if active else self.border_color_inactive
        )
        background_color = "#2C2C2C" if active else "#1E1E1E"
        return f"""
            border: 3px solid {border_color};
            padding: 5px;
            border-radius: {self.size // 2}px;
            min-width: {self.size}px;
            min-height: {self.size}px;
            font-size: {self.font_size}px;
            color: {border_color};
            background-color: {background_color};
        """

    def update_values(self, pin_values):
        """
        Update the display to reflect the current pin values.

        Args:
            pin_values (list): List of pin values (1 or 0).
        """
        for label, value in zip(self.input_labels, pin_values):
            if label.text() != str(value):
                label.setText(str(value))
                label.setStyleSheet(self._get_stylesheet(active=bool(value)))


# Timer Phase
class Timer(Thread):
    def __init__(self, value, display, gui=None, name="Timer"):
        super().__init__(name=name, daemon=True)
        self._value = value
        self._display = display
        self._paused = False
        self._running = False
        self._gui = gui

    def apply_penalty(self):
        self._value = max(0, self._value - PENALTY_TIME)

    def update(self):
        self._min = f"{self._value // 60}".zfill(2)
        self._sec = f"{self._value % 60}".zfill(2)

    def run(self):
        self._running = True
        while self._running and self._value > 0:
            if not self._paused:
                self.update()
                self._display.print(str(self))
                sleep(1)
                self._value -= 1
                if self._value <= 0 and self._gui:
                    self._gui.signal_game_over()
            else:
                sleep(0.1)
        self._running = False

    def pause(self):
        self._paused = not self._paused

    def __str__(self):
        return f"{self._min}:{self._sec}"


# Toggles Phase
class Toggles(Thread):
    def __init__(self, pins, gui, name="Toggles"):
        super().__init__(name=name, daemon=True)
        self._value = ""
        self._pins = pins
        self._gui = gui
        self._solution, self._math_problem = self.generate_solution()
        self._running = True
        self._solved = False

    def generate_solution(self):
        problems = [
            ("2 ** 3 + 3", 2**3 + 3),
            ("4 * 3 - 2", 4 * 3 - 2),
            ("5 + 2 ** 2", 5 + 2**2),
        ]
        problem, answer = random.choice(problems)
        return format(answer, "04b"), problem

    def run(self):
        while self._running:
            current_values = [int(pin.value) for pin in self._pins]
            # Update the GUI input display -- NEED TO FIX COUPLING
            self._gui.toggle_input_display.update_values(current_values)
            self._value = "".join(map(str, current_values))
            if self._value == self._solution:
                self._solved = True
                self._running = False
            sleep(0.1)


class Button(Thread):
    def __init__(self, state, rgb, gui, name="Button"):
        super().__init__(name=name, daemon=True)
        self._state = state
        self._rgb = rgb
        self._gui = gui
        self._running = True
        self._solved = False

    def run(self):
        while self._running:
            if self._state.value:
                self._solved = True
                self._running = False
            sleep(0.1)


# Keypad Phase
class Keypad(Thread):
    def __init__(self, keypad, gui, name="Keypad"):
        super().__init__(name=name, daemon=True)
        self._keypad = keypad
        self._value = ""
        self._equation, self._solution = self.generate_equation()
        self._gui = gui
        self._running = True
        self._solved = False

    def generate_equation(self):
        while True:
            num1 = bin(random.randint(1, 255))[2:]
            num2 = bin(random.randint(1, 255))[2:]
            decimal_result = int(num1, 2) * int(num2, 2)
            if 1000 <= decimal_result <= 9999:
                return (num1, num2), decimal_result

    def run(self):
        print("Solution:", self._solution)
        while self._running:
            if self._keypad.pressed_keys:
                key = self._keypad.pressed_keys[0]
                self._keypad.clear_keys()

                if key == "#":
                    self._value = self._value[:-1]
                elif key == "*":
                    if self._value and int(self._value) == self._solution:
                        self._solved = True
                        self._running = False
                    else:
                        self._value = ""
                        self._gui.timer.apply_penalty()
                        self._gui.phase_status.setText(f"Wrong! -{PENALTY_TIME}s penalty")
                        self._gui.phase_status.setStyleSheet("font-family: 'Verdana'; font-size: 20px; color: red;")
                elif len(self._value) < 4:
                    self._value += str(key)
                
                display_value = self._value + " " * (4 - len(self._value))
                self._gui.keypad_input_display.update_values(display_value)
            sleep(0.1)


# Wires Phase
class Wires(Thread):
    def __init__(self, pins, gui, name="Wires"):
        super().__init__(name=name, daemon=True)
        self._pins = pins
        self._gui = gui

        self._questions = [
            {
                "question": "What year was the University of Tampa founded?",
                "choices": ["A. 1940", "B. 1931", "C. 1933", "D. 1924", "E. 2005"],
                "correct": "B",
            },
            {
                "question": "What was the first cause of a computer bug?",
                "choices": [
                    "A. Syntax error",
                    "B. Logic error",
                    "C. Server crash",
                    "D. A real life bug",
                    "E. None",
                ],
                "correct": "D",
            },
            {
                "question": "First school with a computer science program?",
                "choices": [
                    "A. Harvard",
                    "B. UPenn",
                    "C. Princeton",
                    "D. MIT",
                    "E. Cambridge",
                ],
                "correct": "E",
            },
            {
                "question": "Who is considered the first programmer?",
                "choices": [
                    "A. Rohan Khanad",
                    "B. Murot Yildiz",
                    "C. Ada Lovelace",
                    "D. Dr. Kancharla",
                    "E. Ricardo",
                ],
                "correct": "C",
            },
        ]

        self._current_question = random.choice(self._questions)
        self._running = True
        self._solved = False
        self._cut_wires = set()  # Track which wires have been cut

    def run(self):
        while self._running:
            self._value = [pin.value for pin in self._pins]

            if not all(pin.value for pin in self._pins):
                for index, pin in enumerate(self._pins):
                    if not pin.value:
                        selected_wire = chr(65 + index)
                        if selected_wire not in self._cut_wires:  # New cut detected
                            self._cut_wires.add(selected_wire)
                            if selected_wire == self._current_question["correct"]:
                                self._solved = True
                                self._running = False
                                break
                            else:
                                self._gui.timer.apply_penalty()
                                self._gui.phase_status.setText(f"Wrong! -{PENALTY_TIME}s penalty")
                                self._gui.phase_status.setStyleSheet("font-family: 'Verdana'; font-size: 20px; color: red;")
            sleep(0.1)


# Game State Manager
class GameState:
    def __init__(self):
        self.current_phase = 1

    def next_phase(self):
        self.current_phase += 1

    def check_phase(self):
        return self.current_phase


# Modern Bomb Defusal GUI
class ModernBombDefusalGUI(QMainWindow):
    def __init__(self, game_state, timer, toggles, button, keypad, wires):
        super().__init__()
        self.setWindowTitle("Bomb Defusal Simulator")
        self.setStyleSheet(
            """
            QMainWindow { background-color: #1E1E1E; }
            QLabel { color: #00FF00; font-family: 'Verdana', monospace; }
            QProgressBar {
                border: 2px solid #00FF00;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk { background-color: #00FF00; }
            QTextEdit {
                background-color: #2D2D2D;
                color: #00FF00;
                border: 1px solid #00FF00;
                font-family: 'Verdana', monospace;
            }
        """
        )

        # Layout Setup
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Phase Label
        self.phase_label = QLabel("")
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_label.setStyleSheet("font-size: 18px; color: #00FF00;")
        main_layout.addWidget(self.phase_label)

        # Timer
        self.timer_label = QLabel("Time Remaining: 05:00")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setFont(QFont("Verdana", 24))
        main_layout.addWidget(self.timer_label)

        self.time_progress = QProgressBar()
        self.time_progress.setMaximum(COUNTDOWN)
        self.time_progress.setValue(COUNTDOWN)
        main_layout.addWidget(self.time_progress)

        # Phases Layout
        phases_layout = QVBoxLayout()
        main_layout.addLayout(phases_layout)

        # Toggles Section
        toggles_widget = QWidget()
        toggles_layout = QVBoxLayout()
        toggles_widget.setLayout(toggles_layout)
        self.toggles_question = QLabel("")
        self.toggles_question.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toggles_question.setStyleSheet(
            "font-family: 'Verdana'; font-size: 24px; font-weight: bold;"
        )
        toggles_layout.addWidget(self.toggles_question)
        self.toggle_input_display = InputDisplay(
            num_pins=4,
            size=100,  # Larger size
            font_size=24,  # Smaller font size
            border_color_active="#00FF00",  # Green for active
            border_color_inactive="#FF0000",  # Red for inactive
        )
        toggles_layout.addWidget(self.toggle_input_display)
        phases_layout.addWidget(toggles_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Button Section
        button_widget = QWidget()
        button_layout = QVBoxLayout()
        button_widget.setLayout(button_layout)
        # Button instruction label
        self.button_instruction = QLabel("Press the button")
        self.button_instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.button_instruction.setStyleSheet(
            "font-family: 'Verdana'; font-size: 24px; font-weight: bold;"
        )
        button_layout.addWidget(self.button_instruction)
        phases_layout.addWidget(button_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Keypad Section
        keypad_widget = QWidget()
        keypad_layout = QVBoxLayout()
        keypad_widget.setLayout(keypad_layout)
        self.keypad_equation = QLabel("")
        self.keypad_equation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.keypad_equation.setStyleSheet(
            "font-family: 'Verdana'; font-size: 24px; font-weight: bold;"
        )
        keypad_layout.addWidget(self.keypad_equation)
        self.keypad_input_display = InputDisplay(
            num_pins=4,
            size=40,  # Smaller size
            font_size=18,  # Smaller font size
            border_color_active="#00FF00",  # Green for active
            border_color_inactive="#FF0000",  # Red for inactive
        )
        keypad_layout.addWidget(self.keypad_input_display)
        phases_layout.addWidget(keypad_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Wires Section
        wires_widget = QWidget()
        wires_layout = QVBoxLayout()
        wires_widget.setLayout(wires_layout)
        self.wires_question = QLabel("")
        self.wires_question.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wires_question.setStyleSheet("font-family: 'Verdana'; font-size: 18px;")
        self.wires_choices = QTextEdit()
        self.wires_choices.setReadOnly(True)
        self.wires_choices.setStyleSheet("font-family: 'Verdana'; font-size: 12x;")
        wires_layout.addWidget(self.wires_question)
        wires_layout.addWidget(self.wires_choices)
        phases_layout.addWidget(wires_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Phase Status
        self.phase_status = QLabel("Unsolved")
        self.phase_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_status.setStyleSheet(
            "font-family: 'Verdana'; font-size: 28px; color: red;"
        )
        main_layout.addWidget(self.phase_status)

        # Game Status
        self.game_status = QLabel("Status: Normal")
        self.game_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.game_status.setStyleSheet(
            "font-family: 'Verdana'; font-size: 32px; text-decoration: underline;"
        )
        main_layout.addWidget(self.game_status)

        # Assign Game Logic
        self.game_state = game_state
        self.timer = timer
        self.toggles = toggles
        self.button = button
        self.keypad = keypad
        self.wires = wires

        # Timer Update
        self.timer_updater = QTimer(self)
        self.timer_updater.timeout.connect(self.update_game_state)
        self.timer_updater.start(100)

    def update_game_state(self):
        """Updates the game state and GUI."""
        if self.timer._running:
            # Transition to the next phase if the current one is solved
            if self.is_phase_solved():
                self.phase_status.setText("Solved")
                self.phase_status.setStyleSheet(
                    "color: green; font-family: 'Verdana'; font-size: 28px; font-weight: bold;"
                )
                self.game_state.next_phase()
                QApplication.processEvents()  # Ensure GUI updates before the delay
                # BOMB DEFUSED
                if self.all_phases_solved():
                    QTimer.singleShot(1000, self.end_game)
                    return
                QTimer.singleShot(1000, self.load_next_phase)
            # Update timer and phase-specific UI
            self.timer_label.setText(f"Time Remaining: {self.timer}")
            self.time_progress.setValue(self.timer._value)
        else:
            self.signal_game_over()

    def is_phase_solved(self):
        """Check if the current phase is solved."""
        current_phase = self.game_state.check_phase()
        if current_phase == 1 and self.toggles._solved:
            return True
        elif current_phase == 2 and self.button._solved:
            return True
        elif current_phase == 3 and self.keypad._solved:
            return True
        elif current_phase == 4 and self.wires._solved:
            return True
        return False

    def load_next_phase(self):
        """Update UI when transitioning to a new phase."""
        self.phase_status.setText("Unsolved")
        self.phase_status.setStyleSheet(
            "color: red; font-family: 'Verdana'; font-size: 28px;"
        )
        self.update_phase_ui()

    def update_phase_ui(self):
        """Set up the UI for the current phase."""
        current_phase = self.game_state.check_phase()
        if current_phase == 1:
            self.phase_label.setText("Phase: 1 - Toggles")
            self.toggles_question.setText(f"Solve: {self.toggles._math_problem}\n")
            self.toggle_input_display.show()
            self.button_instruction.hide()
            self.keypad_equation.hide()
            self.keypad_input_display.hide()
            self.wires_question.hide()
            self.wires_choices.hide()
        elif current_phase == 2:
            self.phase_label.setText("Phase: 2 - Button")
            self.toggle_input_display.hide()
            self.toggles_question.hide()
            self.button_instruction.show()
            self.keypad_equation.hide()
            self.keypad_input_display.hide()
            self.wires_question.hide()
            self.wires_choices.hide()
        elif current_phase == 3:
            self.phase_label.setText("Phase: 3 - Keypad")
            self.keypad_equation.setText(
                f"Multiply: {self.keypad._equation[0]} x {self.keypad._equation[1]}"
            )
            self.toggle_input_display.hide()
            self.toggles_question.hide()
            self.button_instruction.hide()
            self.keypad_equation.show()
            self.keypad_input_display.show()
            self.wires_question.hide()
            self.wires_choices.hide()
        elif current_phase == 4:
            self.phase_label.setText("Phase: 4 - Wires")
            self.wires_question.setText(self.wires._current_question["question"])
            self.wires_choices.setText(
                "\n".join(self.wires._current_question["choices"])
            )
            self.toggle_input_display.hide()
            self.toggles_question.hide()
            self.button_instruction.hide()
            self.keypad_equation.hide()
            self.keypad_input_display.hide()
            self.wires_question.show()
            self.wires_choices.show()

    def all_phases_solved(self):
        """Checks if all phases are solved."""
        return self.toggles._solved and self.button._solved and self.keypad._solved and self.wires._solved

    def end_game(self):
        """The user has successfully defused the bomb"""
        self.toggle_input_display.hide()
        self.toggles_question.hide()
        self.button_instruction.hide()
        self.keypad_equation.hide()
        self.keypad_input_display.hide()
        self.wires_question.hide()
        self.wires_choices.hide()
        self.phase_label.setText("BOMB DEFUSED!")
        self.phase_label.setStyleSheet(
            "color: green; font-family: 'Verdana'; font-size: 60px; font-weight: bold; text-decoration: underline;"
        )
        self.phase_status.hide()
        self.time_progress.hide()
        self.timer._running = False  # NEED TO FIX
        self.game_status.hide()
        self.timer_updater.stop()

    def signal_game_over(self):
        self.toggle_input_display.hide()
        self.toggles_question.hide()
        self.button_instruction.hide()
        self.keypad_equation.hide()
        self.keypad_input_display.hide()
        self.wires_question.hide()
        self.wires_choices.hide()
        self.phase_label.setText("BOMB EXPLODED!")
        self.phase_label.setStyleSheet(
            "color: red; font-family: 'Verdana'; font-size: 60px; font-weight: bold; text-decoration: underline;"
        )
        self.phase_status.hide()
        self.time_progress.hide()
        self.timer._running = False  # NEED TO FIX
        self.timer_label.setStyleSheet("color: red;")
        self.game_status.hide()
        self.timer_updater.stop()


# """
# Keyboard Listener
def on_press(key):
    try:
        if key.char in pin_key_map:
            pin = pin_key_map[key.char]
            if isinstance(pin, MockPin):
                pin.toggle()
                print(f"Key '{key.char}' toggled pin. New state: {pin.value}")
            elif isinstance(pin, MockMatrixKeypad):
                keypad_key = keypad_key_map[key.char]
                pin.simulate_key_press(keypad_key)
    except AttributeError:
        pass
# """


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)

        # Initialize game state and objects
        game_state = GameState()
        # i2c = board.I2C()
        # seg7_display = Seg7x4(i2c)
        # seg7_display.brightness = 0.5
        seg7_display = MockSeg7x4()
        timer = Timer(COUNTDOWN, seg7_display)
        gui = ModernBombDefusalGUI(game_state, timer, None, None, None, None)

        # Initialize Toggles
        # toggle_pins = [
        #     DigitalInOut(i) for i in (board.D12, board.D16, board.D20, board.D21)
        # ]
        toggle_pins = [MockPin() for _ in range(4)]
        for pin in toggle_pins:
            pin.direction = Direction.INPUT
            pin.pull = Pull.DOWN
        toggles = Toggles(toggle_pins, gui)
        gui.toggles = toggles

        # Initialize Button
        # button_input = DigitalInOut(board.D4)
        # button_RGB = [DigitalInOut(i) for i in (board.D17, board.D27, board.D22)]
        button_input = MockPin()
        button_RGB = [MockPin() for _ in range(3)]
        button_input.direction = Direction.INPUT
        button_input.pull = Pull.DOWN
        for pin in button_RGB:
            pin.direction = Direction.OUTPUT
            pin.value = True
        button = Button(button_input, button_RGB, gui)
        gui.button = button

        # Initialize Keypad
        # keypad_cols = [DigitalInOut(i) for i in (board.D10, board.D9, board.D11)]
        # keypad_rows = [
        #     DigitalInOut(i) for i in (board.D5, board.D6, board.D13, board.D19)
        # ]
        keypad_cols = [MockPin() for _ in range(3)]
        keypad_rows = [MockPin() for _ in range(4)]
        keypad_keys = ((1, 2, 3), (4, 5, 6), (7, 8, 9), ("*", 0, "#"))
        # matrix_keypad = Matrix_Keypad(keypad_rows, keypad_cols, keypad_keys)
        matrix_keypad = MockMatrixKeypad(keypad_rows, keypad_cols, keypad_keys)
        keypad = Keypad(matrix_keypad, gui)
        gui.keypad = keypad

        # Initialize Wires
        # wire_pins = [
        #     DigitalInOut(i)
        #     for i in (board.D14, board.D15, board.D18, board.D23, board.D24)
        # ]
        wire_pins = [MockPin(True) for _ in range(5)]
        for pin in wire_pins:
            pin.direction = Direction.INPUT
            pin.pull = Pull.DOWN
        wires = Wires(wire_pins, gui)
        gui.wires = wires

        # Assign game state threads
        gui.timer = timer
        gui.toggles = toggles
        gui.button = button
        gui.keypad = keypad
        gui.wires = wires

        # """
        # keyboard mapping for mock input
        pin_key_map = {
            'u': toggle_pins[0],
            'i': toggle_pins[1],
            'o': toggle_pins[2],
            'p': toggle_pins[3],
            'h': button_input,
            'j': button_RGB[0],
            'k': button_RGB[1],
            'l': button_RGB[2],
            'a': wire_pins[0],
            'b': wire_pins[1],
            'c': wire_pins[2],
            'd': wire_pins[3],
            'e': wire_pins[4],
            '7': matrix_keypad,  # Keypad key 7
            '8': matrix_keypad,  # Keypad key 8
            '9': matrix_keypad,  # Keypad key 9
            '4': matrix_keypad,  # Keypad key 4
            '5': matrix_keypad,  # Keypad key 5
            '6': matrix_keypad,  # Keypad key 6
            '1': matrix_keypad,  # Keypad key 1
            '2': matrix_keypad,  # Keypad key 2
            '3': matrix_keypad,  # Keypad key 3
            '0': matrix_keypad,  # Keypad key 0
            '*': matrix_keypad,  # Keypad special key '*'
            '#': matrix_keypad   # Keypad special key '#'
        }
        keypad_key_map = {
            '7': 7, '8': 8, '9': 9,
            '4': 4, '5': 5, '6': 6,
            '1': 1, '2': 2, '3': 3,
            '0': 0, '*': '*', '#': '#'
        }
        # Start Keyboard Listener
        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        # """

        # Start the threads
        timer.start()
        toggles.start()
        button.start()
        keypad.start()
        wires.start()

        # Run the application
        gui.show()
        gui.update_phase_ui()
        sys.exit(app.exec())
    except Exception as e:
        traceback.print_exc()
