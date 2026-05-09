package helper

import (
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestShouldTreatEventStreamResponseAsStream_JSONBodyPreservesBody(t *testing.T) {
	resp := &http.Response{
		Header: http.Header{"Content-Type": []string{"text/event-stream"}},
		Body:   io.NopCloser(strings.NewReader(`{"id":"resp_1","object":"chat.completion"}`)),
	}

	require.False(t, ShouldTreatEventStreamResponseAsStream(resp, false))

	body, err := io.ReadAll(resp.Body)
	require.NoError(t, err)
	require.JSONEq(t, `{"id":"resp_1","object":"chat.completion"}`, string(body))
}

func TestShouldTreatEventStreamResponseAsStream_SSECommentAndDataPreservesBody(t *testing.T) {
	bodyText := ": keepalive\n\ndata: {\"id\":1}\n\ndata: [DONE]\n"
	resp := &http.Response{
		Header: http.Header{"Content-Type": []string{"text/event-stream"}},
		Body:   io.NopCloser(strings.NewReader(bodyText)),
	}

	require.True(t, ShouldTreatEventStreamResponseAsStream(resp, false))

	body, err := io.ReadAll(resp.Body)
	require.NoError(t, err)
	require.Equal(t, bodyText, string(body))
}
