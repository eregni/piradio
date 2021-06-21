#!/bin/bash
PATH=/sbin:/usr/bin:/usr/local/bin:$HOME/wiringPi/gpio:
PIRADIO_ACTIVE=0
PIRADIO_PIN=24

gpio -g mode $PIRADIO_PIN in

while [ 1 ]; do
  if [ "$(gpio -g read $PIRADIO_PIN)" = "1" ]; then
    if $PIRADIO_ACTIVE; then
        sudo -u pi systemctl start piradio
        PIRADIO_ACTIVE=1
    else
      sudo -u pi systemctl stop piradio
      PIRADIO_ACTIVE=0
    fi
  fi
  /bin/sleep 0.25
done

exit 0
