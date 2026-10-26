package com.enervision.telemetry.mapper;

import com.enervision.telemetry.api.dto.PredictionPointResponse;
import com.enervision.telemetry.entity.Prediction;
import com.enervision.telemetry.entity.PredictionRun;
import org.springframework.stereotype.Component;

@Component
public class PredictionMapper {

	public PredictionPointResponse toResponse(Prediction prediction) {
		PredictionRun run = prediction.getRun();
		return new PredictionPointResponse(prediction.getPredictedFor(), prediction.getPredictionKwh(),
				run.getRunId(), run.getModelName(), run.getModelVersion(), run.getGeneratedAt());
	}

}
