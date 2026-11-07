#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2014 Paul Kinsella <kali.gsm.rtl.sdr@gmail.com>
# Modifikasi & Integrasi GUI wxPython, Realtime Datetime, dan Error Handling PDU

from datetime import datetime
import glob
import sys
import time
import serial
import serial.tools.list_ports
import wx

###################################
#   Serial setup global
###################################
mySerialPort = serial.Serial()
mySerialPort.port = "COM4"  # default port
mySerialPort.baudrate = 115200
mySerialPort.bytesize = serial.EIGHTBITS
mySerialPort.parity = serial.PARITY_NONE
mySerialPort.stopbits = serial.STOPBITS_ONE
mySerialPort.timeout = 1  # non-blocking/timeout 1 detik
mySerialPort.xonxoff = False
mySerialPort.rtscts = False
mySerialPort.dsrdtr = False

# Character sets untuk GSM 7-bit default alphabet & extension
gsm = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
       "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ`¿abcdefghijklmnopqrstuvwxyzäöñüà")
ext = ("````````````````````^```````````````````{}`````\\````````````[~]`"
       "|````````````````````````````````````€``````````````````````````")

WAP_TYPE = [
    "01", "02", "03", "04", "05", "06", "07", "08",
    "09", "0A", "0B", "0C", "0D", "0E", "0F"
]

#################################
# Return serial ports list
#################################
def getOpenSerialPorts():
    result = []
    ports = serial.tools.list_ports.comports()
    for p in ports:
        result.append(p.device)
        
    if not result and sys.platform.startswith('win'):
        for i in range(1, 256):
            port_name = f"COM{i}"
            try:
                s = serial.Serial(port_name)
                s.close()
                result.append(port_name)
            except (serial.SerialException, OSError):
                pass
    elif not result and sys.platform.startswith('linux'):
        temp_list = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyS*')
        for a_port in temp_list:
            try:
                s = serial.Serial(a_port)
                s.close()
                result.append(a_port)
            except (serial.SerialException, OSError):
                pass
    return result

########################################################################
#   GET BACK AN AT COMMAND REPLY
########################################################################
def getAtReply(serial_port, at_command):
    ser_temp = serial.Serial()
    ser_temp.port = serial_port
    if not ser_temp.isOpen():
        ser_temp.open()
    time.sleep(0.3)
    ress = ""
    if ser_temp.isOpen():
        ser_temp.flushInput()
        ser_temp.flushOutput()
        ser_temp.write((at_command + "\r").encode())
        time.sleep(0.3)
        bytesToRead = ser_temp.inWaiting()
        ress = ser_temp.read(bytesToRead).decode(errors='ignore')
        ser_temp.close()
    return ress

###############################################################################
#   SWAPS NUMBER EVERY 2 DIGITS USED FOR PDU
#############################################################################
def swapNumber(number):
    swaparray = []
    returnNumber = ""
    first1, first2 = 0, 1
    second1, second2 = 1, 2

    for x in range(0, len(number) // 2):
        swaparray.append(number[second1:second2])
        swaparray.append(number[first1:first2])
        first1 += 2
        first2 += 2
        second1 += 2
        second2 += 2

    for num in swaparray:
        returnNumber += num
    return returnNumber 

###############################################################################
#   ENCODE SMS TEXT TO GSM
#############################################################################
def gsm_encode(plaintext):
    res = bytearray()
    for c in plaintext:
        idx = gsm.find(c)
        if idx != -1:
            res.append(idx)
            continue
        idx = ext.find(c)
        if idx != -1:
            res.append(27)
            res.append(idx)
    return res.hex().upper()

def gsm_encode8bit(SMS):
    return gsm_encode(SMS)

def stringToHex(str2hex):
    return str2hex.encode('utf-8').hex().upper()

def stringToHex18bit(str2hex):
    hexbuffer = ""
    for c in str2hex:
        hexbuffer += f"00{c.encode('utf-8').hex()}"
    return hexbuffer.upper()

########################################################################
#           CREATE PDU STRING
########################################################################
def createPduString(phone_num, sms_text, message_type, del_report_status):
    NUMBER_LEN = len(phone_num)
    NUMBER = phone_num
    SMS_TYPE = message_type

    if NUMBER_LEN % 2 != 0:
        NUMBER += "F"

    NUMBER = swapNumber(NUMBER)
    NUMBER_LEN_HEX = f"{NUMBER_LEN:02X}"

    smslen = len(sms_text) * 2
    MSG_LEN_HEX = f"{smslen:02X}"

    DEL_REPORT = "21" if del_report_status else "01"
    decodedstr1 = stringToHex18bit(sms_text)

    PDU_STRING = f"00{DEL_REPORT}00{NUMBER_LEN_HEX}91{NUMBER}00{SMS_TYPE}{MSG_LEN_HEX}{decodedstr1}"
    return PDU_STRING

########################################################################
#           CREATE WAP PUSH PDU STRING
########################################################################
def createWapPduString(start_date, end_date, header, target_num, msg, wap_type):
    NUMBER = target_num 
    NUMBER_LEN = len(target_num)
    NUMBER_LEN_HEX = f"{NUMBER_LEN:02X}"
    
    if NUMBER_LEN % 2 != 0:
        NUMBER += "F"

    NUMBER = swapNumber(NUMBER)

    smslen = len(msg) + 66  
    MSG_LEN_HEX = f"{smslen:02X}"

    WAP_PDU_STRING = (
        f"004100{NUMBER_LEN_HEX}91{NUMBER}0004{MSG_LEN_HEX}"
        f"0B05040B84C0020003F001010B060403AE81EA02056A0045C6{wap_type}"
        f"03{stringToHex(header)}000AC306{start_date}10C306{end_date}0103{stringToHex(msg)}00"
    )
    return WAP_PDU_STRING

########################################################################
#           GUI FRAME CLASS
########################################################################
class ExampleFrame(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, size=(260, 420), title='Wap Push Sender')
        panel = wx.Panel(self)

        tested_ports = getOpenSerialPorts()
        if len(tested_ports) < 1:
            tested_ports.append("NO PORTS")

        # Waktu realtime sistem (Format: YYYYMMDDHHMM)
        current_realtime = datetime.now().strftime('%Y%m%d%H%M')

        # --- UI CONTROLS ---
        self.lb_comport = wx.StaticText(panel, label="Com Port:", pos=(5, 5))
        self.combo_serial_ports = wx.ComboBox(
            panel, size=(145, 30), pos=(80, 5), 
            choices=tested_ports, style=wx.CB_READONLY
        )
        self.combo_serial_ports.SetSelection(0)

        self.lb_start_date = wx.StaticText(panel, label="Start Date:", pos=(5, 35))
        self.edit_start_date = wx.TextCtrl(panel, size=(145, 30), pos=(80, 35), value=current_realtime)

        self.lb_end_date = wx.StaticText(panel, label="End Date:", pos=(5, 65))
        self.edit_end_date = wx.TextCtrl(panel, size=(145, 30), pos=(80, 65), value=current_realtime)

        self.lb_header = wx.StaticText(panel, label="Header:", pos=(5, 95))
        self.edit_header = wx.TextCtrl(panel, size=(145, 30), pos=(80, 95), value='[www.headerhere.com](https://www.headerhere.com)')

        self.lb_target = wx.StaticText(panel, label="Target No:", pos=(5, 125))
        self.edit_target_number = wx.TextCtrl(panel, size=(145, 30), pos=(80, 125), value='123456789012')

        self.lb_target_data = wx.StaticText(panel, label="Sms Msg:", pos=(5, 155))
        self.edit_target_msg = wx.TextCtrl(
            panel, size=(145, 50), pos=(80, 155), 
            value='Hello World', style=wx.TE_MULTILINE
        )

        self.btnpdumode = wx.Button(panel, label="Pdu Mode", pos=(5, 215), size=(80, 30))
        self.combo_wap_types = wx.ComboBox(
            panel, pos=(90, 215), size=(65, 30), 
            choices=WAP_TYPE, style=wx.CB_READONLY
        )
        self.combo_wap_types.SetSelection(11)

        self.btnsend = wx.Button(panel, label="Send", pos=(160, 215), size=(65, 30))

        self.lb_output = wx.StaticText(panel, label="Debug:", pos=(5, 250))
        self.edit_debug = wx.TextCtrl(
            panel, size=(225, 90), pos=(5, 270), 
            value='', style=wx.TE_MULTILINE
        )

        # --- EVENT BINDINGS ---
        self.btnpdumode.Bind(wx.EVT_BUTTON, self.onPduModeClick)
        self.btnsend.Bind(wx.EVT_BUTTON, self.onSendClick)

    def onPduModeClick(self, event):
        port_name = self.combo_serial_ports.GetValue()
        reply = getAtReply(port_name, "AT+CMGF=0")
        wx.MessageBox(str(reply), 'PDU Mode Info', wx.OK | wx.ICON_INFORMATION)

    def onSendClick(self, event):
        mySerialPort.port = self.combo_serial_ports.GetValue()
        
        # Generate WAP Push PDU String
        WAP_PDU_STRING = createWapPduString(
            self.edit_start_date.GetValue(),
            self.edit_end_date.GetValue(),
            self.edit_header.GetValue(),
            self.edit_target_number.GetValue(),
            self.edit_target_msg.GetValue(),
            self.combo_wap_types.GetValue()
        )

        self.edit_debug.SetValue(WAP_PDU_STRING)

        try:
            if not mySerialPort.is_open:
                mySerialPort.open()

            if mySerialPort.is_open:
                mySerialPort.reset_input_buffer()
                mySerialPort.reset_output_buffer()
                
                # 1. Atur PDU Mode (AT+CMGF=0)
                mySerialPort.write(b"AT+CMGF=0\r")
                time.sleep(0.3)
                
                # 2. Hitung panjang oktet PDU dinamis (Mengabaikan byte SMSC di awal jika dihitung dari string heksadesimal total)
                # Panjang oktet PDU yang dikirim ke +CMGS adalah total panjang byte hex dibagi 2 dikurangi panjang SMSC (biasanya 1 byte '00' di awal = kurangi 1)
                pdu_length = int(len(WAP_PDU_STRING) / 2) - 1
                
                # 3. Kirim perintah AT+CMGS dengan panjang dinamis untuk menghindari Error 304
                command = f"AT+CMGS={pdu_length}\r"
                mySerialPort.write(command.encode('utf-8'))
                time.sleep(0.5)
                
                # 4. Kirim string PDU dan akhiri dengan karakter Ctrl+Z (\x1A)
                mySerialPort.write(WAP_PDU_STRING.encode('utf-8') + b"\x1A")
                time.sleep(1.5)
                
                bytesToRead = mySerialPort.in_waiting
                ress = mySerialPort.read(bytesToRead).decode('utf-8', errors='ignore')
                
                if not ress:
                    ress = "Pesan terkirim (tidak ada respons teks balik dari modem)."

                wx.MessageBox(ress, 'Status Pengiriman', wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox('Gagal membuka port serial.', 'Error', wx.OK | wx.ICON_ERROR)

        except Exception as e:
            wx.MessageBox(f'Serial Error: {str(e)}', 'Error', wx.OK | wx.ICON_ERROR)
            
        finally:
            if mySerialPort.is_open:
                mySerialPort.close()


if __name__ == '__main__':
    app = wx.App(False)
    frame = ExampleFrame(None)
    frame.Show()
    app.MainLoop()
