package helper

import (
	"bytes"
	"io"
	"net/http"
	"strings"
)

type UpstreamEventStreamProbeResult int

const (
	UpstreamEventStreamProbeUnknown UpstreamEventStreamProbeResult = iota
	UpstreamEventStreamProbeSSE
	UpstreamEventStreamProbeNotSSE
)

const upstreamEventStreamProbeBytes = 1024

var eventStreamLinePrefixes = [][]byte{
	[]byte("data:"),
	[]byte("event:"),
	[]byte("id:"),
	[]byte("retry:"),
	[]byte(":"),
	[]byte("[DONE]"),
}

func ShouldTreatEventStreamResponseAsStream(resp *http.Response, clientRequestedStream bool) bool {
	if clientRequestedStream {
		return true
	}
	if resp == nil || resp.Body == nil {
		return false
	}
	if !strings.HasPrefix(strings.ToLower(resp.Header.Get("Content-Type")), "text/event-stream") {
		return false
	}

	result, err := ProbeUpstreamEventStreamBody(resp, upstreamEventStreamProbeBytes)
	if err != nil || result == UpstreamEventStreamProbeUnknown {
		return true
	}
	return result == UpstreamEventStreamProbeSSE
}

func ProbeUpstreamEventStreamBody(resp *http.Response, maxBytes int) (UpstreamEventStreamProbeResult, error) {
	if resp == nil || resp.Body == nil {
		return UpstreamEventStreamProbeUnknown, nil
	}
	if maxBytes <= 0 {
		maxBytes = upstreamEventStreamProbeBytes
	}

	originalBody := resp.Body
	buffer := make([]byte, 0, maxBytes)
	temp := make([]byte, 256)

	defer func() {
		resp.Body = io.NopCloser(io.MultiReader(bytes.NewReader(buffer), originalBody))
	}()

	for len(buffer) < maxBytes {
		readLimit := len(temp)
		remaining := maxBytes - len(buffer)
		if remaining < readLimit {
			readLimit = remaining
		}

		n, err := originalBody.Read(temp[:readLimit])
		if n > 0 {
			buffer = append(buffer, temp[:n]...)
			if result := detectEventStreamPrefix(buffer); result != UpstreamEventStreamProbeUnknown {
				return result, nil
			}
		}

		if err != nil {
			if err == io.EOF {
				return detectEventStreamPrefix(buffer), nil
			}
			return UpstreamEventStreamProbeUnknown, err
		}
		if n == 0 {
			return detectEventStreamPrefix(buffer), nil
		}
	}

	return detectEventStreamPrefix(buffer), nil
}

func detectEventStreamPrefix(sample []byte) UpstreamEventStreamProbeResult {
	trimmed := bytes.TrimLeft(sample, "\xef\xbb\xbf \t\r\n")
	if len(trimmed) == 0 {
		return UpstreamEventStreamProbeUnknown
	}

	if trimmed[0] == '{' {
		return UpstreamEventStreamProbeNotSSE
	}
	if bytes.HasPrefix(trimmed, []byte("[")) && !bytes.HasPrefix(trimmed, []byte("[DONE]")) {
		return UpstreamEventStreamProbeNotSSE
	}

	for _, rawLine := range bytes.Split(trimmed, []byte("\n")) {
		line := bytes.TrimSpace(rawLine)
		if len(line) == 0 {
			continue
		}
		for _, prefix := range eventStreamLinePrefixes {
			if bytes.HasPrefix(line, prefix) {
				return UpstreamEventStreamProbeSSE
			}
		}
		if line[0] == '{' {
			return UpstreamEventStreamProbeNotSSE
		}
		if bytes.HasPrefix(line, []byte("[")) && !bytes.HasPrefix(line, []byte("[DONE]")) {
			return UpstreamEventStreamProbeNotSSE
		}
		return UpstreamEventStreamProbeUnknown
	}

	return UpstreamEventStreamProbeUnknown
}
