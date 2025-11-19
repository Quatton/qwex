package main

import (
	"fmt"
	"os"
	"runtime/debug"

	"github.com/quatton/qwex/apps/qwexctl/cmd"
)

func main() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Fprintf(os.Stderr, "qwexctl crashed: %v\n", r)
			if os.Getenv("QWEX_DEBUG") != "" {
				debug.PrintStack()
			}
			os.Exit(2)
		}
	}()

	cmd.Execute()
}
