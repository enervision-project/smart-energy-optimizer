# Build context: repository root (docker build -f services/core-api/Dockerfile .)

# Build: Maven build of all modules, produces the executable jar
FROM docker.io/library/eclipse-temurin:27-jdk AS build
WORKDIR /build
COPY services/core-api/ .
# Maven repository cache between builds (BuildKit)
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -q package -DskipTests

# Runtime: JRE only + jar
FROM docker.io/library/eclipse-temurin:27-jre
WORKDIR /app
COPY --from=build /build/bootstrap/target/bootstrap-*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
