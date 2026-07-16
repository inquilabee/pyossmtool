#!/usr/bin/env bash
# Intentionally sloppy script for shellcheck demo.

unused_var="hello"

if [ "$1" = "test" ]; then
	echo $unused_var
	rm -rf $1/*
fi
