"""Decode absolute HID touch fields and inject into the virtual compositor."""
import ctypes
import fcntl
import os
import struct
import socket


def touch_layout(descriptor):
    page=0; size=count=0; report=0; maximum=0; usages=[]; low=high=None
    offsets={}; layouts={}; contacts={}; stack=[]; i=0
    while i<len(descriptor):
        prefix=descriptor[i]; i+=1
        if prefix==254:
            if i+2>len(descriptor): raise ValueError('truncated HID long item')
            n=descriptor[i]; i+=2+n; continue
        n=(0,1,2,4)[prefix&3]
        if i+n>len(descriptor): raise ValueError('truncated HID item')
        value=int.from_bytes(descriptor[i:i+n],'little'); i+=n
        kind=(prefix>>2)&3; tag=prefix>>4
        if kind==1:
            if tag==0: page=value
            elif tag==2: maximum=value
            elif tag==7: size=value
            elif tag==8: report=value
            elif tag==9: count=value
            elif tag==10: stack.append((page,size,count,report,maximum))
            elif tag==11:
                if not stack: raise ValueError('unbalanced HID globals')
                page,size,count,report,maximum=stack.pop()
        elif kind==2:
            if tag==0: usages.append((page,value))
            elif tag==1: low=value
            elif tag==2: high=value
        elif kind==0:
            if tag==8:
                if size>32 or count>256: raise ValueError('oversized HID field')
                offset=offsets.get(report,0)
                if low is not None and high is not None:
                    usages.extend((page,u) for u in range(low,min(high,low+255)+1))
                for k in range(count):
                    usage=usages[min(k,len(usages)-1)] if usages else None
                    name={(1,0x30):'x',(1,0x31):'y',(13,0x33):'down',(13,0x42):'down',(13,0x34):'cancel'}.get(usage)
                    if name and not value&1 and value&2 and not value&4:
                        fields=layouts.setdefault(report,{})
                        if name in fields:
                            contacts.setdefault(report,[]).append(fields)
                            fields={}; layouts[report]=fields
                        fields[name]=(offset+k*size,size,maximum)
                offsets[report]=offset+size*count
            usages=[]; low=high=None
    result={}
    for report,fields in layouts.items():
        complete=[f for f in contacts.get(report,[])+[fields] if all(k in f for k in ('x','y','down'))]
        if complete:
            result[report]=dict(complete[0])
            if len(complete)>1: result[report]['_contacts']=complete
    return result


def decode_touch(layouts, data, width=1920,height=720):
    report=data[0] if layouts and 0 not in layouts and data else 0
    fields=layouts.get(report)
    if not fields: raise ValueError('unknown touch report')
    body=data[1:] if report else data
    raw=int.from_bytes(body,'little')
    # A mouse represents one active contact. Do not overwrite the first
    # finger with a second, inactive contact from a multitouch descriptor.
    candidates=fields.get('_contacts',[fields])
    def pressed(candidate):
        offset,size,_=candidate['down']
        if offset+size>len(body)*8: raise ValueError('short touch report')
        return (raw>>offset)&((1<<size)-1)
    fields=next((candidate for candidate in candidates if pressed(candidate)),candidates[0])
    def field(name):
        offset,size,maximum=fields[name]
        if offset+size>len(body)*8 or not size: raise ValueError('short touch report')
        return (raw>>offset)&((1<<size)-1),maximum
    x,xmax=field('x'); y,ymax=field('y'); down,_=field('down')
    if not xmax or not ymax: raise ValueError('invalid touch range')
    if 'cancel' in fields and field('cancel')[0]: down=0
    return bool(down),min(width-1,x*(width-1)//xmax),min(height-1,y*(height-1)//ymax)
