# scala/build

`pipelines/scala/build.yaml` builds Scala libraries without sbt. It reads a
`scala-build` file in the format of Debian's
[dh-scala](https://salsa.debian.org/mendezr/dh-scala) (`scala-build(5)`):
one stanza per artifact and Scala binary version, with the source
directories, compiler options and class path copied from upstream's
`build.sbt`.

```yaml
environment:
  contents:
    packages:
      - openjdk-25-default-jdk
      - scala-2.13      # one compiler per Scala-Version used
      - scala-3.8

pipeline:
  - uses: git-checkout
    with: ...
  - uses: scala/build   # reads packages/<name>/scala-build
```

`packages/scala-xml.yaml` is an example: one source built for Scala 3,
2.13 and 2.12.

## Inputs

| Input | Default | |
|-------|---------|---|
| `config` | `${{package.name}}/scala-build` | File to read, relative to the source directory |
| `version` | `${{package.version}}` | Version of stanzas without `Version` |
| `destdir` | `${{targets.contextdir}}` | Where stanzas without `Package` are installed |
| `outdir` | `${{targets.outdir}}` | Parent directory of the packages named by `Package` |
| `java-opts` | `-Xss16m` | JVM options for the compiler |

## Differences from dh-scala

The fields and their meaning are the same. Debian-specific parts change:

- **Compilers.** `scala-2.12` and `scala-2.13` from this repository, and
  Wolfi's `scala-3.x` for `Scala-Version: 3`.
- **Package** names a melange package of the recipe (main package or
  subpackage). Without it, the jar goes to the package being built.
- **Version** defaults to the recipe version.
- **Classpath** `group:artifact` without a version uses the only version
  in `/usr/share/maven-repo`, or `debian` if present.
- **POM.** `poms/<id>.pom.xml` next to the `scala-build` file, if it exists.
  The minimal POM lists the dependencies with their versions.
- **Install** layout, without maven-repo-helper:

  ```
  /usr/share/java/<id>-<version>.jar
  /usr/share/java/<id>.jar -> <id>-<version>.jar
  /usr/share/maven-repo/<group>/<id>/<version>/<id>-<version>.{pom,jar}
  ```

The jars are reproducible as in dh-scala: manifest first, sorted entries,
all dated `SOURCE_DATE_EPOCH`.

`debian-to-melange` turns `dh --buildsystem=scala` into this pipeline and
copies `debian/scala-build` next to the recipe.

## Tests

```bash
python3 -m unittest discover -s scripts
```
