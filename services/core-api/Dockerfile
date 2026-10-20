# Contexte de build : racine du dépôt (docker build -f services/core-api/Dockerfile .)

# Build : compilation Maven de tous les modules, produit le jar exécutable
FROM docker.io/library/eclipse-temurin:21-jdk AS build
WORKDIR /build
COPY services/core-api/ .
# cache du dépôt Maven entre deux builds (BuildKit)
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -q package -DskipTests

# Runtime : JRE seul + jar
FROM docker.io/library/eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/application/target/application-*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
