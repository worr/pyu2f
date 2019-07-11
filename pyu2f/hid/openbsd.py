# Copyright 2019 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Implements raw hid interface on OpenBSD with character devices"""

import ctypes
import fcntl
import os
import os.path
from ctypes import (Structure, c_char, c_int, c_int32, c_uint8, c_uint16,
                    c_uint32, c_void_p)

from . import base

USB_GET_DEVICEINFO = 0x421c5570

# /usr/include/dev/usb/usb.h
USB_MAX_DEVICES = 128
USB_MAX_STRING_LEN = 127
USB_MAX_DEVNAMES = 4
USB_MAX_DEVNAMELEN = 16


class UsbDeviceInfo(Structure):
    _fields_ = [
        ('udi_bus', c_uint8),
        ('udi_addr', c_uint8),
        ('udi_product', c_char * USB_MAX_STRING_LEN),
        ('udi_vendor', c_char * USB_MAX_STRING_LEN),
        ('udi_release', c_char * 8),
        ('udi_productNo', c_uint16),
        ('udi_vendorNo', c_uint16),
        ('udi_releaseNo', c_uint16),
        ('udi_class', c_uint8),
        ('udi_subclass', c_uint8),
        ('udi_protocol', c_uint8),
        ('udi_config', c_uint8),
        ('udi_speed', c_uint8),
        ('udi_power', c_int),
        ('udi_nports', c_int),
        ('udi_devnames', c_char * USB_MAX_DEVNAMELEN * USB_MAX_DEVNAMES),
        ('udi_ports', c_uint8 * 8),
        ('udi_serial', c_char * USB_MAX_STRING_LEN),
    ]


class HidItem(Structure):
    _fields_ = [
        ('_usage_page', c_uint32),
        ('logical_minimum', c_int32),
        ('logical_maximum', c_int32),
        ('physical_minimum', c_int32),
        ('physical_maximum', c_int32),
        ('unit_exponent', c_int32),
        ('unit', c_int32),
        ('report_size', c_int32),
        ('report_ID', c_int32),
        ('report_count', c_int32),
        ('usage', c_uint32),
        ('usage_minimum', c_int32),
        ('usage_maximum', c_int32),
        ('designator_index', c_int32),
        ('designator_minimum', c_int32),
        ('designator_maximum', c_int32),
        ('string_index', c_int32),
        ('string_minimum', c_int32),
        ('string_maximum', c_int32),
        ('set_delimiter', c_int32),
        ('collection', c_int32),
        ('collevel', c_int),
        ('kind', c_int),
        ('flags', c_uint32),
        ('pos', c_uint32),
        ('next', c_void_p),
    ]


def ReadReportDescriptor(device_fd, desc):
    libusbhid = ctypes.CDLL("/usr/lib/libusbhid.so.7.0")
    libusbhid.hid_get_report_desc.restype = c_void_p
    libusbhid.hid_start_parse.restype = c_void_p

    rdesc = libusbhid.hid_get_report_desc(device_fd)
    if rdesc == None:
        raise Error("Cannot get report descriptor")

    hiddata = libusbhid.hid_start_parse(c_void_p(rdesc), 1 << 3, 0)
    if hiddata == None:
        libusbhid.hid_dispose_report_desc(c_void_p(rdesc))
        raise Error("Cannot get hiddata")

    desc.internal_max_in_report_len = libusbhid.hid_report_size(
        c_void_p(rdesc), 0, 0)
    desc.internal_max_out_report_len = libusbhid.hid_report_size(
        c_void_p(rdesc), 1, 0)

    hiditem = HidItem()
    res = libusbhid.hid_get_item(c_void_p(hiddata), ctypes.byref(hiditem))
    if res < 0:
        libusbhid.hid_dispose_report_desc(c_void_p(rdesc))
        raise Error("Cannot get hiddata")
    desc.usage_page = (hiditem.usage & 0xffff0000) >> 16
    desc.usage = hiditem.usage & 0x0000ffff

    libusbhid.hid_dispose_report_desc(c_void_p(rdesc))


class OpenBSDHidDevice(base.HidDevice):
    @staticmethod
    def Enumerate():
        for dev in os.listdir('/dev/'):
            if not dev.startswith('uhid'):
                continue
            try:
                path = os.path.join('/dev', dev)
                with open(path) as f:
                    dev_info = UsbDeviceInfo()
                    fcntl.ioctl(f, USB_GET_DEVICEINFO, dev_info)

                    has_uhid = False
                    uhid_name = ""

                    desc = base.DeviceDescriptor()
                    desc.vendor_id = int(dev_info.udi_vendorNo)
                    desc.vendor_string = dev_info.udi_vendor.decode('utf-8')
                    desc.product_id = int(dev_info.udi_productNo)
                    desc.product_string = dev_info.udi_product.decode('utf-8')
                    desc.path = path
                    ReadReportDescriptor(f.fileno(), desc)
                yield desc.ToPublicDict()
            except OSError as e:
                pass

    def __init__(self, path):
        base.HidDevice.__init__(self, path)
        self.desc = base.DeviceDescriptor()
        self.desc.path = path
        self.dev = os.open(self.desc.path, os.O_RDWR)
        ReadReportDescriptor(self.dev, self.desc)

    def GetInReportDataLength(self):
        return self.desc.internal_max_in_report_len

    def GetOutReportDataLength(self):
        return self.desc.internal_max_out_report_len

    def Write(self, packet):
        out = bytearray(packet)
        print(out)
        os.write(self.dev, out)

    def Read(self):
        raw_in = os.read(self.dev, self.GetInReportDataLength())
        decoded_in = list(bytearray(raw_in))
        return decoded_in
