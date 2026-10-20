// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>

// Fetch the repository's indexes and key through its address as Go clients
// (apko, melange) do: net/http follows redirects and sends a Referer, which
// SourceForge answers with an HTML page instead of the file. Exits 1 if an
// index is not a signed gzip, or the key is not served directly.
//
//	go run ./scripts/repository-url-check [https://wolfi.vejeta.com]
package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
)

func get(url string) (*http.Response, []byte, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	return resp, body, err
}

func checkIndex(url string) error {
	resp, body, err := get(url)
	if err != nil {
		return err
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("HTTP %d from %s", resp.StatusCode, resp.Request.URL)
	}
	gz, err := gzip.NewReader(bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("not gzip (%s, from %s)", resp.Header.Get("Content-Type"), resp.Request.URL)
	}
	tr := tar.NewReader(gz)
	for {
		h, err := tr.Next()
		if err != nil {
			return fmt.Errorf("no signature in the index from %s", resp.Request.URL)
		}
		if h.Name == ".SIGN.RSA.vejeta-wolfi.rsa.pub" {
			fmt.Printf("ok: %s (signed, from %s)\n", url, resp.Request.URL.Host)
			return nil
		}
	}
}

func checkKey(url string) error {
	resp, body, err := get(url)
	if err != nil {
		return err
	}
	if resp.Request.URL.String() != url {
		return fmt.Errorf("the key is redirected to %s; it should be served by the address itself", resp.Request.URL)
	}
	if resp.StatusCode != 200 || !strings.Contains(string(body), "BEGIN PUBLIC KEY") {
		return fmt.Errorf("HTTP %d, not a public key", resp.StatusCode)
	}
	fmt.Printf("ok: %s (served directly)\n", url)
	return nil
}

func main() {
	base := "https://wolfi.vejeta.com"
	if len(os.Args) > 1 {
		base = strings.TrimRight(os.Args[1], "/")
	}
	failed := false
	for _, arch := range []string{"x86_64", "aarch64"} {
		if err := checkIndex(base + "/" + arch + "/APKINDEX.tar.gz"); err != nil {
			fmt.Println("FAIL:", arch, err)
			failed = true
		}
	}
	if err := checkKey(base + "/keys/vejeta-wolfi.rsa.pub"); err != nil {
		fmt.Println("FAIL:", err)
		failed = true
	}
	if failed {
		os.Exit(1)
	}
}
