# Suppress .pyc files
import sys
sys.dont_write_bytecode = True

import socket
import struct
import subprocess

# Generate the protobuf file from vendor/audiokinetic/services/VHALInjection
# It is recommended to use the protoc provided in: prebuilts/tools/common/m2/repository/com/google/protobuf/protoc/3.0.0
# or a later version, in order to provide Python 3 compatibility
#   protoc -I=proto --python_out=proto proto/AkVehicleHalProto.proto
import AkVHALInjector.AkVehicleHalProto_pb2 as AkVehicleHalProto_pb2

# Hard-coded socket port needs to match the one in the VHALInjectionServer
REMOTE_PORT_NUMBER = 33455

# VehiclePropertyType
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

class vhal_types_2_0:
    TYPE_STRING  = [VEHICLEPROPERTYTYPE_STRING]
    TYPE_BYTES   = [VEHICLEPROPERTYTYPE_BYTES]
    TYPE_INT32   = [VEHICLEPROPERTYTYPE_BOOLEAN,
                    VEHICLEPROPERTYTYPE_INT32]
    TYPE_INT64   = [VEHICLEPROPERTYTYPE_INT64]
    TYPE_FLOAT   = [VEHICLEPROPERTYTYPE_FLOAT]
    TYPE_INT32S  = [VEHICLEPROPERTYTYPE_INT32_VEC]
    TYPE_INT64S  = [VEHICLEPROPERTYTYPE_INT64_VEC]
    TYPE_FLOATS  = [VEHICLEPROPERTYTYPE_FLOAT_VEC]
    TYPE_MIXED   = [VEHICLEPROPERTYTYPE_MIXED]


# If container is a dictionary, retrieve the value for key item;
# Otherwise, get the attribute named item out of container
def getByAttributeOrKey(container, item, default=None):
    if isinstance(container, dict):
        try:
            return container[item]
        except KeyError as e:
            return default
    try:
        return getattr(container, item)
    except AttributeError as e:
        return default

class AkVHALInjector:
    """
        Dictionary of prop_id to value_type.  Used by setProperty() to properly format data.
    """
    _propToType = {}

    ### Private Functions
    def _txCmd(self, cmd):
        """
            Transmits a protobuf to Android Auto device.  Should not be called externally.
        """
        # Serialize the protobuf into a string
        msgStr = cmd.SerializeToString()
        msgLen = len(msgStr)
        # Convert the message length into int32 byte array
        msgHdr = struct.pack('!I', msgLen)
        # Send the message length first
        self.sock.sendall(msgHdr)
        # Then send the protobuf
        self.sock.sendall(msgStr)

    ### Public Functions
    def openSocket(self, device=None, port=REMOTE_PORT_NUMBER):
        """
            Connects to an Android Auto device running the Wwise VHALInjectionServer.
        """
        extraArgs = '' if device is None else '-s %s' % device
        adbCmd = 'adb %s forward tcp:0 tcp:%d' % (extraArgs, port)
        adbResp = subprocess.check_output(adbCmd, shell=True)[0:-1]
        localPortNumber = int(adbResp)
        print('Connecting local port %s to remote port %s on %s' % (
            localPortNumber, port,
            'default device' if device is None else 'device %s' % device))
        # Open the socket and connect
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(('localhost', localPortNumber))

    def rxMsg(self):
        """
            Receive a message over the socket.  This function blocks if a message is not available.
        """
        # Receive the message length (int32) first
        b = self.sock.recv(4)
        if (len(b) == 4):
            msgLen, = struct.unpack('!I', b)
            if (msgLen > 0):
                # Receive the actual message
                b = self.sock.recv(msgLen)
                if (len(b) == msgLen):
                    # Unpack the protobuf
                    msg = AkVehicleHalProto_pb2.InjectionMessage()
                    msg.ParseFromString(b)
                    return msg
                else:
                    print("Ignored message fragment")

    def getConfig(self, prop):
        """
            Sends a getConfig message for the specified property.
        """
        cmd = AkVehicleHalProto_pb2.InjectionMessage()
        cmd.msg_type = AkVehicleHalProto_pb2.GET_CONFIG_CMD
        propGet = cmd.prop.add()
        propGet.prop = prop
        self._txCmd(cmd)

    def getConfigAll(self):
        """
            Sends a getConfigAll message to the host.  This will return all configs available.
        """
        cmd = AkVehicleHalProto_pb2.InjectionMessage()
        cmd.msg_type = AkVehicleHalProto_pb2.GET_CONFIG_ALL_CMD
        self._txCmd(cmd)

    def getProperty(self, prop, area_id):
        """
            Sends a getProperty command for the specified property ID and area ID.
        """
        cmd = AkVehicleHalProto_pb2.InjectionMessage()
        cmd.msg_type = AkVehicleHalProto_pb2.GET_PROPERTY_CMD
        propGet = cmd.prop.add()
        propGet.prop = prop
        propGet.area_id = area_id
        self._txCmd(cmd)

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

    def setProperty(self, prop, area_id, value):
        """
            Sends a setProperty command for the specified property ID, area ID, and value.
              This function chooses the proper value field to populate based on the config for the
              property.  It is the caller's responsibility to ensure the value data is the proper
              type.
        """
        cmd = AkVehicleHalProto_pb2.InjectionMessage()
        cmd.msg_type = AkVehicleHalProto_pb2.SET_PROPERTY_CMD
        propValue = cmd.value.add()
        propValue.prop = prop
        # Insert value into the proper area
        propValue.area_id = area_id
        # Determine the value_type and populate the correct value field in protoBuf
        try:
            valType = self._propToType[prop]
        except KeyError:
            raise ValueError('propId is invalid:', prop)
            return
        
        # if the data is a string or bytes and the property is INT64_VEC, wrap the data in INT64
        if isinstance(value, str) or isinstance(value, bytes) and valType in vhal_types_2_0.TYPE_INT64S:
            value = self._wrapBytesInInt64(value)

        propValue.value_type = valType
        if valType in vhal_types_2_0.TYPE_STRING:
            propValue.string_value = value
        elif valType in vhal_types_2_0.TYPE_BYTES:
            propValue.bytes_value = value
        elif valType in vhal_types_2_0.TYPE_INT32:
            propValue.int32_values.append(value)
        elif valType in vhal_types_2_0.TYPE_INT64:
            propValue.int64_values.append(value)
        elif valType in vhal_types_2_0.TYPE_FLOAT:
            propValue.float_values.append(value)
        elif valType in vhal_types_2_0.TYPE_INT32S:
            propValue.int32_values.extend(value)
        elif valType in vhal_types_2_0.TYPE_INT64S:
            propValue.int64_values.extend(value)
        elif valType in vhal_types_2_0.TYPE_FLOATS:
            propValue.float_values.extend(value)
        elif valType in vhal_types_2_0.TYPE_MIXED:
            propValue.string_value = \
                getByAttributeOrKey(value, 'string_value', '')
            propValue.bytes_value = \
                getByAttributeOrKey(value, 'bytes_value', '')
            for newValue in getByAttributeOrKey(value, 'int32_values', []):
                propValue.int32_values.append(newValue)
            for newValue in getByAttributeOrKey(value, 'int64_values', []):
                propValue.int64_values.append(newValue)
            for newValue in getByAttributeOrKey(value, 'float_values', []):
                propValue.float_values.append(newValue)
        else:
            raise ValueError('value type not recognized:', valType)
            return
        self._txCmd(cmd)

    def __init__(self, serial=None, port=REMOTE_PORT_NUMBER):
        # Open the socket
        self.openSocket(serial, port)
        # Get the list of configs
        self.getConfigAll()
        msg = self.rxMsg()
        # Parse the list of configs to generate a dictionary of prop_id to type
        for cfg in msg.config:
            self._propToType[cfg.prop] = cfg.value_type
