package xtable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.stream.Stream;

final class LakeFiles {

    private LakeFiles() {
    }

    static void run(String label) throws IOException {
        Path root = Path.of(Paths.TABLE);
        List<String> lines;
        try (Stream<Path> walk = Files.walk(root)) {
            lines = walk.filter(Files::isRegularFile)
                    .map(file -> root.relativize(file).toString() + "\t" + size(file) + "\t" + sha256(file))
                    .sorted()
                    .toList();
        }
        Paths.write("files_" + label + ".tsv", lines);
        System.out.println("listed " + lines.size() + " files as " + label);
    }

    private static long size(Path file) {
        try {
            return Files.size(file);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String sha256(Path file) {
        try (InputStream in = Files.newInputStream(file)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[8192];
            int read;
            while ((read = in.read(buffer)) > 0) {
                digest.update(buffer, 0, read);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (IOException | NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
