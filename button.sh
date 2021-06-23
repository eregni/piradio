#!/bin/bash
PATH=/sbin:/usr/bin:/usr/local/bin:$HOME/wiringPi/gpio:
PIRADIO_ACTIVE=false
PIRADIO_PIN=24

gpio -g mode $PIRADIO_PIN in
gpio -g mode $PIRADIO_PIN up
systemctl stop piradio
while true; do
  if [ "$(gpio -g read $PIRADIO_PIN)" = "0" ]; then
    if $PIRADIO_ACTIVE; then
      systemctl stop piradio
      PIRADIO_ACTIVE=false
    else
      systemctl start piradio
      PIRADIO_ACTIVE=true
    fi
  fi
  /bin/sleep 0.25
done

exit 0
