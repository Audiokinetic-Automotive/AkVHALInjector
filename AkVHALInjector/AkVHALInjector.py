import AkVHALInjector.adb as adb
import subprocess

VEHICLEPROPERTYTYPE_STRING = 0x100000
VEHICLEPROPERTYTYPE_BOOLEAN = 0x200000
VEHICLEPROPERTYTYPE_INT32 = 0x400000
VEHICLEPROPERTYTYPE_INT32_VEC = 0x410000
VEHICLEPROPERTYTYPE_INT64 = 0x500000
VEHICLEPROPERTYTYPE_INT64_VEC = 0x510000
VEHICLEPROPERTYTYPE_FLOAT = 0x600000
VEHICLEPROPERTYTYPE_FLOAT_VEC = 0x610000
VEHICLEPROPERTYTYPE_BYTES = 0x700000
VEHICLEPROPERTYTYPE_MIXED = 0xe00000
VEHICLEPROPERTYTYPE_MASK = 0xff0000

class AkVHALInjector:
    def __init__(self, serial: str | None = None):
        self.device = adb.get_device(serial=serial)
        self.shell = self.device.shell_popen(
            ["sh"], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
        # print the serial number of the device
        print(self.device.serial)
        self.propertyTypes = self._getAllPropertiesTypes()
        self._startAkWwiseCli()

    def _sendShellCommand(self, command, waitforoutput = False):
        # send a command to the shell and appends another command so we know when the first command is finished
        command = command + "\n"
        self.shell.stdin.write(command.encode('utf-8'))
        self.shell.stdin.flush()
        output = ""
        # print(command)
        if waitforoutput:
            command = "echo \"AKVHALINJECTORCOMMANDFINISHED\"\n"
            self.shell.stdin.write(command.encode('utf-8'))
            self.shell.stdin.flush()

            # read from stdout and accumulate the output until the command is finished
            while True:
                line = self.shell.stdout.readline().strip().decode('utf-8')
                if line == "AKVHALINJECTORCOMMANDFINISHED":
                    break
                output += line + "\n"
        else:
            self.shell.stdout.flush()

        return output

    def _startAkWwiseCli(self):
        self._sendShellCommand("akwwisecli --basepath foobar")

    def _stopAkWwiseCli(self):
        self._sendShellCommand("exit")

    def _sanitizeInteger(self, data):
        # if the data is already an integer, return it
        if isinstance(data, int):
            return data
        # make sure the data is an integer
        # if a hex value is passed, convert it to an integer
        base = 10
        if data.startswith("0x"):
            base = 16
            data = data[2:]
        try:
            return int(data, base=base)
        except ValueError:
            print("Invalid integer value")
            return None

    def _getPropertyType(self, propertyId):
        propertyId = self._sanitizeInteger(propertyId)
        propertyType = propertyId & VEHICLEPROPERTYTYPE_MASK
        return propertyType

    def _getAllPropertiesTypes(self):
        command = f"cmd car_service get-carpropertyconfig"
        output = self._sendShellCommand(command, waitforoutput=True)
        properties = {}
        for line in output.split("\n"):
            if line.startswith("Property:"):
                propertyId = line.split(",")[0].split(":")[1]
                propertyId = self._sanitizeInteger(propertyId)
                properties[propertyId] = self._getPropertyType(propertyId)
        return properties

    def _wrapBytesInInt64(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        dataLength = len(data)
        if dataLength % 8 != 0:
            padding = 8 - (dataLength % 8)
            data += b"\0" * padding
        elif isinstance(data, str):
            data = data + b"\0"
        data = [int.from_bytes(data[i:i+8], byteorder='little', signed=True) for i in range(0, len(data), 8)]
        data = [dataLength] + data
        return data

    def setProperty(self, propertyId, areaId, data):
        propertyId = self._sanitizeInteger(propertyId)
        areaId = self._sanitizeInteger(areaId)
        
        # check if the property exists and is in the dictionary
        if propertyId not in self.propertyTypes:
            print("Property not found in the target device")
            return

        # if the data is a string or bytes and the property is INT64_VEC, wrap the data in INT64
        if isinstance(data, str) or isinstance(data, bytes) and self.propertyTypes[propertyId] == VEHICLEPROPERTYTYPE_INT64_VEC:
            data = self._wrapBytesInInt64(data)

        if self.propertyTypes[propertyId] == VEHICLEPROPERTYTYPE_INT32_VEC or self.propertyTypes[propertyId] == VEHICLEPROPERTYTYPE_INT64_VEC or self.propertyTypes[propertyId] == VEHICLEPROPERTYTYPE_FLOAT_VEC:
            # if the data is a list, convert it to a string
            if isinstance(data, list):
                dataLength = len(data)
                data = " ".join([str(i) for i in data])
                data = f"{dataLength} {data}"
            else:
                print("Invalid data type")
                return

        command = f"setvhalprop 0x{propertyId:02x} 0x{areaId:02x} {data}\n"
        self._sendShellCommand(command)
