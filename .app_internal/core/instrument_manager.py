"""Opens, closes, and safes the Keithley and Numato connections."""
from instruments.keithley2460 import find_keithley, keithley_output_safe
from instruments.numato_relay import find_numato, all_pixels_disconnect


def make_safe(keithley, relay, logger=None):
    if keithley is not None:
        try:
            keithley_output_safe(keithley)
        except Exception as e:
            if logger:
                logger(f"WARNING: could not turn Keithley output off: {e}")
    if relay is not None:
        try:
            all_pixels_disconnect(relay)
        except Exception as e:
            if logger:
                logger(f"WARNING: could not open relays: {e}")


class InstrumentManager:
    def __init__(self, mock=False):
        self.keithley = None
        self.relay = None
        self.mock = mock

    def close_all(self):
        for inst in (self.keithley, self.relay):
            if inst is not None:
                try:
                    inst.close()
                except Exception:
                    pass
        self.keithley = None
        self.relay = None

    def connect_all(self, logger=None):
        self.close_all()

        if self.mock:
            from instruments.mock_keithley import MockKeithley
            from instruments.mock_relay import MockRelay

            self.keithley = MockKeithley()
            self.relay = MockRelay()
            if logger:
                logger("OK: Keithley connected (MOCK)")
                logger(f"OK: Numato relay connected on {self.relay.port} (MOCK)")
            return True, True

        try:
            self.keithley = find_keithley(logger=logger)
            if logger:
                logger("OK: Keithley connected")
        except Exception as e:
            if logger:
                logger(f"ERROR: Keithley connection failed: {e}")

        try:
            self.relay = find_numato(logger=logger)
            if logger:
                logger(f"OK: Numato relay connected on {self.relay.port}")
        except Exception as e:
            if logger:
                logger(f"ERROR: Relay connection failed: {e}")

        return self.keithley is not None, self.relay is not None
