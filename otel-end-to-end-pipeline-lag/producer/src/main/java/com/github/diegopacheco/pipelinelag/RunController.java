package com.github.diegopacheco.pipelinelag;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/runs")
public class RunController {

    private final RunRegistry registry;

    public RunController(RunRegistry registry) {
        this.registry = registry;
    }

    @GetMapping
    public List<RunStats> all() {
        return registry.all();
    }

    @PostMapping("/{runId}")
    public ResponseEntity<RunStats> start(@PathVariable String runId, @RequestParam(defaultValue = "50") int rate) {
        return registry.start(runId, rate)
                .map(stats -> ResponseEntity.status(HttpStatus.CREATED).body(stats))
                .orElseGet(() -> ResponseEntity.status(HttpStatus.CONFLICT).build());
    }

    @GetMapping("/{runId}")
    public ResponseEntity<RunStats> stats(@PathVariable String runId) {
        return ResponseEntity.of(registry.stats(runId));
    }

    @DeleteMapping("/{runId}")
    public ResponseEntity<RunStats> stop(@PathVariable String runId) throws InterruptedException {
        return ResponseEntity.of(registry.stop(runId));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> badRequest(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(e.getMessage());
    }
}
