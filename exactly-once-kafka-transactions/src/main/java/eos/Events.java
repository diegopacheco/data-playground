package eos;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

final class Events {
    private static final Path FILE = Settings.RUN.resolve("events.tsv");

    static void log(String scenario, String message) {
        String line = System.currentTimeMillis() + "\t" + scenario + "\t" + message + "\n";
        try {
            Files.writeString(FILE, line, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        System.out.print(line);
    }

    static List<String> all() throws IOException {
        return Files.exists(FILE) ? Files.readAllLines(FILE) : List.of();
    }
}
