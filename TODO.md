* Would be very nice for manifest files to have a .nspawn file section
  that's just raw text dropped into /etc/systemd/nspawn/$MACHINE.nspawn

  * Remember to ensure that /etc/systemd/nspawn/ actually exists and make it
    if it does not.  That directory doesn't seem to get auto-created by the RPM.

  * Remember to remove the .nspawn file when using the salmon delete command.
