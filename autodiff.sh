#!/usr/bin/env bash 
# for the 'rg' command: sudo apt install ripgrep 
# Args $1 and $2 are the old and new versions of the APK, respectively. 
# Argument 3 ($3) is an optional file with one function per line, in the following format (java.lang.object.toString() used as an example): 
# -> <java.lang.Object: java.lang.String toString()>
# Lines not in this format are ignored. 
apktool d $1 -o old 1>&2 && zip -FSr -9 old.zip ./old/ 1>&2 && rm -rf old & 
apktool d $2 -o new 1>&2 && zip -FSr -9 new.zip ./new/ 1>&2 && rm -rf new &
wait; 
if [[ $3 != "" ]]; then 
	python C:/Users/joeya/Documents/NJIT-Resources/Research/apkcracking/anrAPK/smalanalysis/sa-list old.zip new.zip all | rg -f <(rg -o -r '$1: .*? $2' "[\s]+-> <(.*?): .*? (.*?)\(" $3 | sort | uniq);
else 
	python C:/Users/joeya/Documents/NJIT-Resources/Research/apkcracking/anrAPK/smalanalysis/sa-list old.zip new.zip all; 
fi
