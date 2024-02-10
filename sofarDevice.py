# =============================================================================================================
#
# @file     sofarDevice.py
# @author   Matthias Klemm <Matthias_Klemm@gmx.net>
# @version  1.0
# @Python   >= 3.2 required
# @date     January, 2024
#
# Based on a script by Michalux: https://github.com/MichaluxPL/Sofar_LSW3
#
# @section  LICENSE
#
# Copyright (C) 2023, Matthias Klemm. All rights reserved.
#
# GNU GENERAL PUBLIC LICENSE
# Version 3, 29 June 2007
#
#
# @brief    A class to implement a modbus communication protocol with a Sofar Solar Inverter (K-TLX)
#           via logger module LSW-3/LSE. Requires IP address, port, serial number of the inverter,
#           total power of the connected pv modules (in kW), and the inverters / loggers protocol definition.
#           Set system size to 0 to disable checking the received data for plausibility.
#

import binascii
import ipaddress
import logging
import socket
import time

import libscrc


class sofarDevice:
    myIP = ''
    myPort = None
    mySerialNumber = None
    mySocket = None
    mySystemSize = 0
    sofarProtocol = dict()
    _connectedToInverterFlag = False

    def __init__(self, ip, port, serial, systemSize, sofarProto):
        # constructor
        if isinstance(ip, str) and ipaddress.ip_address(ip):
            self.myIP = ip
        else:
            raise RuntimeError("input argument \'ip\' expected to a valid ip address, got %s instead.", str(ip))
        if isinstance(port, int) or isinstance(port, float):
            self.myPort = int(port)
        else:
            raise RuntimeError("input argument \'port\' expected to be a number, got %s instead.", type(port))
        if isinstance(serial, int) or isinstance(serial, float):
            self.mySerialNumber = int(serial)
        else:
            raise RuntimeError("input argument \'serial\' expected to be a number, got %s instead.", type(serial))
        if isinstance(systemSize, int) or isinstance(systemSize, float):
            self.mySystemSize = float(systemSize)
        else:
            raise RuntimeError("input argument \'systemSize\' expected to be a number, got %s instead.", type(systemSize))
        if isinstance(sofarProto, dict):
            self.sofarProtocol = sofarProto
        else:
            raise RuntimeError("input argument \'protocol\' expected to be a dict, got %s instead.", type(sofarProto))

    def __enter__(self):
        # for with-statement
        return self


    def __del__(self):
        # destructor
        if(self.mySocket):
            try:
                self.mySocket.close()
            except Exception as err:
                return


    def __exit__(self, exc_type, exc_value, traceback):
        # for with-statement
        if (self.mySocket):
            try:
                self.mySocket.close()
            except Exception as err:
                return


    @staticmethod
    def padhex(s):
        return '0x' + s[2:].zfill(4)

    @staticmethod
    def hex_zfill(intval):
        hexvalue = hex(intval)
        return '0x' + str(hexvalue)[2:].zfill(4)

    @staticmethod
    def isValidString(s):
        return bool(isinstance(s, str) and s and not s.isspace())


    def _connect(self):
        # OPEN SOCKET
        self.mySocket = []
        self._connectedToInverterFlag = False
        for res in socket.getaddrinfo(self.myIP, self.myPort, socket.AF_INET, socket.SOCK_STREAM):
            family, socktype, proto, canonname, sockadress = res
            try:
                self.mySocket = socket.socket(family, socktype, proto)
                self.mySocket.settimeout(15)
                self.mySocket.connect(sockadress)
                self._connectedToInverterFlag = True
            except socket.error as msg:
                logging.error(
                    'Could not open socket ' + self.myIP + ':' + str(self.myPort) + ' - inverter (' + str(
                        self.mySerialNumber) + ') turned off? Message: ' + msg.strerror)
                print('Could not open socket ' + self.myIP + ':' + str(self.myPort) + ' - inverter (' + str(
                    self.mySerialNumber) + ') turned off? Message: ' + msg.strerror)
                break
        if not self._connectedToInverterFlag:
            # connection failed -> wait a bit and try again
            return False

    def _generateRequest(self, regRangeDef):
        # generate request for inverter to send register data
        if 'registerStart' not in regRangeDef or 'registerEnd' not in regRangeDef:
            logging.error('register range definition does not contain start and/or end register')
            return False
        # generate modbus request
        regStart = int(regRangeDef['registerStart'], 0)
        regEnd = int(regRangeDef['registerEnd'], 0)
        requestBytes = bytearray(36)
        requestBytes[0:1] = binascii.unhexlify('A5')  # Logger Start code
        requestBytes[1:3] = binascii.unhexlify('1700')  # Logger frame DataLength
        requestBytes[3:5] = binascii.unhexlify('1045')  # Logger ControlCode
        requestBytes[5:7] = binascii.unhexlify('0000')  # Serial
        requestBytes[7:11] = bytearray.fromhex(
            hex(self.mySerialNumber)[8:10] + hex(self.mySerialNumber)[6:8] + hex(self.mySerialNumber)[4:6] + hex(self.mySerialNumber)[2:4])
        requestBytes[11:26] = binascii.unhexlify(
            '020000000000000000000000000000')  # com.igen.localmode.dy.instruction.send.SendDataField
        # Data logger frame begin
        # Modbus request begin
        businessfield = binascii.unhexlify(
            '0003' + str(self.hex_zfill(regStart)[2:]) + str(
                self.hex_zfill(regEnd - regStart + 1)[2:]))  # Modbus data to count crc
        requestBytes[26:32] = businessfield
        requestBytes[32:34] = binascii.unhexlify(str(self.padhex(hex(libscrc.modbus(businessfield)))[4:6]) + str(
            self.padhex(hex(libscrc.modbus(businessfield)))[2:4]))  # CRC16modbus
        # compute checksum
        checksum = 0
        for i in range(1, 34, 1):
            checksum += requestBytes[i] & 255
        requestBytes[34] = int((checksum & 255))
        requestBytes[35:36] = binascii.unhexlify('15')  # Logger End code
        return requestBytes

    def getRegisterRangeData(self, requestedRegRangeDefs):
        # read a register range from the inverter and return its values
        # make sure requested register ranges are valid
        if self.isValidString(requestedRegRangeDefs):
            requestedRegRangeDefs = [requestedRegRangeDefs]
        requestedRegRangeDefs = list(set(requestedRegRangeDefs))  # only unique list items
        requiredRegRanges = ['EnergyTodayTotals', 'PVOutput']
        for reqRange in requiredRegRanges:
            if reqRange not in requestedRegRangeDefs:
                requestedRegRangeDefs += [requiredRegRanges[0]]
        for reqRange in requestedRegRangeDefs:
            if reqRange not in self.sofarProtocol:
                requestedRegRangeDefs.remove(reqRange)
        # allow up to 10 retries to connect to the inverter and obtain the data
        maxRetries = 10
        for retryCounter in range(1, maxRetries, 1):
            logging.debug('Inverter communication try #%d', retryCounter)
            # check connection
            if not self._connectedToInverterFlag:
                self._connect()
                if not self._connectedToInverterFlag:
                    # no connection -> wait a bit and retry
                    time.sleep(10)
                    continue
            # connection established
            logging.info('Successfully connected to inverter (' + str(self.mySerialNumber) + ') at ' + self.myIP + ':' + str(self.myPort))
            output = {}
            for regRangeName in requestedRegRangeDefs:
                regRangeDef = self.sofarProtocol[regRangeName]
                requestBytes = self._generateRequest(regRangeDef)
                # send request for register range to inverter
                try:
                    self.mySocket.sendall(requestBytes)
                except Exception as err:
                    logging.error("Sending request to inverter failed: ", err)
                    self.mySocket.close()
                    self._connectedToInverterFlag = False
                    break
                logging.debug("Sent request to inverter: %s", str(requestBytes))
                # give the inverter some time to send data back
                time.sleep(1)
                # read the answer from the inverter
                regRangeVals = self._readRegisterRange(regRangeDef)
                if regRangeVals and isinstance(regRangeDef, dict):
                    output[regRangeName] = regRangeVals
                else:
                    self.mySocket.close()
                    self._connectedToInverterFlag = False
                    break
            # collected all data or some sort of error occurred
            if not self._connectedToInverterFlag:
                # something went wrong -> retry
                time.sleep(10)
                continue
            # sanity check of the received data
            for regRangeName in requestedRegRangeDefs:
                if regRangeName not in output:
                    # required registers have not been read from the inverter
                    self.mySocket.close()
                    self._connectedToInverterFlag = False
                    time.sleep(10)
                    continue
            power_total = output['PVOutput']['Power_PV1'] + output['PVOutput']['Power_PV2']
            if self.mySystemSize and (output['EnergyTodayTotals']['PV_Generation_Today'] > 10 * self.mySystemSize or power_total > 1200 * self.mySystemSize):
                # this value does not make sense, wait a bit and try again
                logging.debug('Value for \'energy today\': ' + str(
                    output['EnergyTodayTotals']['PV_Generation_Today']) + ' or \'power\': ' + str(
                    power_total) + ' too large - retrying...')
                self.mySocket.close()
                self._connectedToInverterFlag = False
                time.sleep(10)
                continue
            else:
                # all done, data seems ok
                return output
        # all trials failed, no data to return
        return False

    def _readRegisterRange(self, regRangeDef):
        # read data transmitted from the inverter
        if not self._connectedToInverterFlag or not self.mySocket:
            return False
        # check if register range is valid
        if 'registerStart' not in regRangeDef or 'registerEnd' not in regRangeDef:
            logging.error('register range definition does not contain start and/or end register')
            return False
        regStart = int(regRangeDef['registerStart'], 0)
        regEnd = int(regRangeDef['registerEnd'], 0)
        # read the answer from the inverter
        okFlag = True
        data = b''
        while okFlag:
            try:
                chunk = self.mySocket.recv(1024)
                # try:
                if not chunk:
                    print("No data received from inverter")
                    logging.error("No data received from inverter")
                    self.mySocket.close()
                    self._connectedToInverterFlag = False
                    break
                data = data + chunk
                if data.__len__() >= (regEnd - regStart + 1) + 60 / 4:
                    # we collected enough data, any data beyond this will not be parsed
                    break
            except socket.timeout as msg:
                logging.debug("Connection timeout - inverter and/or gateway is offline: %s", msg)
                break
            except Exception as err:
                logging.debug("Connection failed: %s", err)
                self._connectedToInverterFlag = False
                break
        if not data:
            # got no data from the inverter -> abort
            self.mySocket.close()
            self._connectedToInverterFlag = False
        if not self._connectedToInverterFlag:
            # connection timed out or receiving data failed -> abort reading data from inverter
            return False
            # break
        # parse data from the inverter
        logging.debug("Data received from inverter: " + str(data))
        output = {}
        for idx in range(0, regEnd - regStart + 1, 1):
            idxStart = 28 + (idx * 2)
            idxEnd16 = idxStart + 2  # 16-bit value
            idxEnd32 = idxStart + 4  # 32-bit value
            if idxEnd16 > len(data):
                break
            hexpos = str("0x") + str(hex(idx + regStart)[2:].zfill(4)).upper()
            if hexpos not in regRangeDef:
                # register not found in register range definition
                continue
            regDef = regRangeDef[hexpos]
            try:
                factor = float(regDef['factor'])
            except:
                factor = 1
            # match regDef['valueType']:  # requires python 3.10
            #     case 'u16':
            #         val = int.from_bytes(data[idxStart:idxEnd16], "big", signed="False") * factor
            #     case 'u32':
            #         val = int.from_bytes(data[idxStart:idxEnd32], "big", signed="False") * factor
            #     case 'i16':
            #         val = int.from_bytes(data[idxStart:idxEnd16], "big", signed="True") * factor
            #     case 'i32':
            #         val = int.from_bytes(data[idxStart:idxEnd32], "big", signed="True") * factor
            #     case _:
            #         continue
            if regDef['valueType'] == 'u16':
                val = int.from_bytes(data[idxStart:idxEnd16], "big", signed="False") * factor
            elif regDef['valueType'] == 'u32':
                val = int.from_bytes(data[idxStart:idxEnd32], "big", signed="False") * factor
            elif regDef['valueType'] == 'i16':
                val = int.from_bytes(data[idxStart:idxEnd16], "big", signed="True") * factor
            elif regDef['valueType'] == 'i32':
                val = int.from_bytes(data[idxStart:idxEnd32], "big", signed="True") * factor
            else:
                continue
            output[regDef['name']] = val
        return output