# Nawam

Bootable USB Creator for Windows.

Copyright © 2026 Shanna Studio.

Website: https://nawam.shanna.id

## Download

Download Nawam.exe from [the releases page](https://github.com/shannacore/nawam/releases).
No installation is required. The download includes a SHA-256 checksum and matching source code.

## Features

- Create bootable USB media from supported Windows and Linux ISO images.
- Choose GPT or MBR and compatible UEFI or Legacy BIOS targets.
- Select the filesystem, cluster size and volume label.
- Monitor progress, status and detailed logs.
- Use portable preferences with nawam.ini.
- Open integrated help and license information.

Available options depend on the selected image, device and Windows version.

## Quick start

1. Back up all important files on the USB device.
2. Run Nawam.exe and check the device name and capacity.
3. Select a trusted ISO image.
4. Review the partition scheme, target system and format options.
5. Click Start only after confirming the correct device.
6. Wait until the operation has completed before unplugging the USB.

Formatting and creating bootable media erase data on the selected device.

## Portable mode

Place an empty file named nawam.ini beside Nawam.exe to keep preferences in that directory.
Use a location where you have write permission.

## Requirements

- Windows x64. Windows 11 is the primary test environment.
- Administrator permission for disk operations.
- A supported ISO and a USB device with sufficient capacity.

## Release notes

Version 1.0.3 simplifies the main header to text only and retains clickable boot-mode help, monitor-aware license layout,
clearer startup warnings and manual security-data refresh independent of executable updates.
The compact download uses executable compression without removing application features.

This build is unsigned. Windows may display Unknown publisher.
Verify the download checksum. Physical USB write and boot tests are not automated.

## Development

Open Nawam.sln or follow [BUILD.md](BUILD.md) for the command-line build.

## License

GPL-3.0-or-later. See [LICENSE.txt](LICENSE.txt) and [NOTICE.md](NOTICE.md).
The application is supplied without warranty. Component notices are also available
under License & Open Source inside Nawam.
