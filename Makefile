raspberry:
	script -q -c "python core/main.py" /dev/null | grep -v -E "Cannot connect|jack server|JackShmReadWritePtr|ALSA|alsa"