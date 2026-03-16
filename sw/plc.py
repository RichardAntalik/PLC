import time
from gfx import Gfx
from plc_io import IO

class PLC:
    """
    A stateless PLC (Programmable Logic Controller) scheduler.
    It separates logic execution (Input/Output processing) from graphics rendering.
    
    Architecture:
    - Logic Cycle: Reads Sensors -> Writes Outputs.
    - Graphics Cycle: Clears Screen -> Draws Sensors -> Draws Outputs -> Draws Generics -> Updates Screen.
    
    Data State is expected to be managed externally (e.g., global variables or data objects).
    """
    def __init__(self, logic_freq=10, gfx_freq=30, fb_device='/dev/fb0'):
        self.gfx = Gfx(fb_device=fb_device)
        self.io = IO()
        self.logic_period = 1.0 / logic_freq
        self.gfx_period = 1.0 / gfx_freq
        
        # Execution Queue
        self.process = []
        
        self.running = False

    def set_background(self, source):
        """Sets the background image or color."""
        self.gfx.set_background(source)

    def sensor_add(self, func):
        """
        Registers a sensor.
        :param logic_func: Function to read hardware/inputs. Runs every logic cycle.
        :param gfx_func: Function to draw state. Runs every graphics cycle. Receives (gfx).
        """
        self.process.append(func)

    def output_add(self, func):
        """
        Registers an output.
        :param logic_func: Function to drive hardware/outputs. Runs every logic cycle.
        :param gfx_func: Function to draw state. Runs every graphics cycle. Receives (gfx).
        """
        self.process.append(func)

    def generic_add(self, func):
        """
        Registers a generic graphics function (e.g., headers, clocks).
        :param gfx_func: Function to draw. Runs every graphics cycle. Receives (gfx).
        """
        self.process.append(func)

    def plc_start(self):
        """Starts the main execution loop."""
        self.running = True
        
        with self.gfx:
            try:
                while self.running:
                    self.gfx.clear()

                    # Process program
                    for fn in self.process:
                        fn(self)
                    
                    self.gfx.update()
                    # Yield CPU
                    time.sleep(0.001)

            except KeyboardInterrupt:
                print("\nStopped by user.")
            finally:
                self.running = False