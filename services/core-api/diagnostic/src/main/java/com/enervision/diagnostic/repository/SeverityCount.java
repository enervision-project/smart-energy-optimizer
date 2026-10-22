package com.enervision.diagnostic.repository;

/**
 * Number of alerts for one raw severity value.
 */
public record SeverityCount(String severity, long count) {
}
