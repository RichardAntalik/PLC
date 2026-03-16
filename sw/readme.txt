To make V0 code work, SPI buffer limit needs to be increased:
  Add spidev.bufsiz=200000 to /boot/firmware/cmdline.txt


V1:
===

sudo nano /boot/config.txt
# Enable SPI Interface
dtparam=spi=on
dtoverlay=fbtft,spi0-0,ili9341,rotate=90,speed=32000000,dc_pin=25,reset_pin=24

Disable terminal cursor in /boot/firmware/cmdline.txt:
vt.global_cursor_default=0

