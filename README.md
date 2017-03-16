Cuckoo DXL Python Service
====================================================

Overview
--------

The Cuckoo DXL Python
service exposes access to Cuckoo's commands via the `Data Exchange Layer <http://www.mcafee.com/us/solutions/data-exchange-layer.aspx>`_ (DXL) fabric.

The following Cuckoo Resources are compatible:

```
tasks/list
tasks/view
tasks/reschedule
tasks/delete
tasks/report
tasks/rereport
files/view
machines/list
machines/view
cuckoo/status
vpn/status
```

The following Cuckoo Resources require POST methods or file transfers
which will be included in a future release:

```
/tasks/create/file
/tasks/create/url
/tasks/screenshots
memory/list
memory/get
files/get
pcap/get
```

LICENSE
-------

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at

`<http://www.apache.org/licenses/LICENSE-2.0>`_
