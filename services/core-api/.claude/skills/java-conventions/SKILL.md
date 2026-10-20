---
name: java-conventions
description: Conventions de code Java et architecture en couches du core-api Enervision (Spring Boot 4, Java 21, monolithe modulaire Maven). À charger avant d'écrire, modifier ou relire du code Java dans services/core-api — nouvelle entité, endpoint REST, service, repository, DTO, mapper, exception ou test — et avant d'ajouter une dépendance Maven ou un module.
---

# Conventions Java — core-api

core-api est un **monolithe modulaire** : un seul jar exécutable (`application`) qui assemble des modules métier Maven (`user`, `diagnostic`, `telemetry`, `configuration`). Chaque module suit la même **architecture en couches** avec interfaces et implémentations. Voir `README.md` pour le build, la base et Docker.

## 1. Architecture en couches

```
Controller  →  Service (interface)  →  Repository (Spring Data)  →  Base
   ↑ DTO          ↑ impl : ServiceImpl        ↑ Entity
```

| Couche | Rôle | Ne fait PAS |
|---|---|---|
| **Controller** (`api`) | HTTP : routes, validation des entrées (`@Valid`), codes de statut, DTO in/out | Pas de logique métier, pas d'accès au repository, n'expose jamais une entité |
| **Service** (`service`) | Logique métier, transactions, orchestration, conversion entité ↔ DTO via le mapper | Ne connaît pas HTTP (`ResponseEntity`, `HttpServletRequest`…) |
| **Repository** (`repository`) | Accès aux données (interfaces Spring Data JPA) | Pas de logique métier |
| **Domain** (`domain`) | Entités JPA, enums métier | Pas de dépendance vers les couches supérieures |

Règles de dépendance : une couche n'appelle que la couche juste en dessous. Le controller dépend de **l'interface** du service, jamais de l'implémentation.

## 2. Structure d'un module

Tout le code d'un module est sous `com.enervision.<module>` (sinon il n'est pas scanné par `com.enervision.Application`).

```
com.enervision.<module>
├── api/
│   ├── <Nom>Controller.java
│   └── dto/                    <Nom>Response, Create<Nom>Request, Update<Nom>Request
├── service/
│   ├── <Nom>Service.java       interface publique du module
│   └── impl/
│       └── <Nom>ServiceImpl.java
├── repository/
│   └── <Nom>Repository.java
├── domain/
│   └── <Nom>.java              entité JPA
├── mapper/
│   └── <Nom>Mapper.java
└── exception/
    └── <Nom>NotFoundException.java
```

## 3. Communication entre modules

- Un module n'utilise un autre module **que via son interface de service et ses DTO** (`com.enervision.<autre>.service.*Service`, `com.enervision.<autre>.api.dto.*`).
- Interdit : injecter le repository, utiliser l'entité ou la classe `impl` d'un autre module.
- La dépendance doit être déclarée dans le `pom.xml` du module appelant. Pas de dépendance cyclique entre modules ; un module métier ne dépend jamais d'`application`.

## 4. Conventions par couche

### Controller

```java
@RestController
@RequestMapping("/api/v1/sites")
@RequiredArgsConstructor
@Tag(name = "Sites")
public class SiteController {

	private final SiteService siteService;

	@GetMapping("/{siteId}")
	public SiteResponse getSite(@PathVariable String siteId) {
		return siteService.getSite(siteId);
	}

	@PostMapping
	@ResponseStatus(HttpStatus.CREATED)
	public SiteResponse createSite(@Valid @RequestBody CreateSiteRequest request) {
		return siteService.createSite(request);
	}

}
```

- Routes préfixées `/api/v1/<ressource-au-pluriel>`, en kebab-case.
- Retourner directement le DTO ; `ResponseEntity` seulement si les en-têtes ou le statut sont dynamiques.
- Documenter avec les annotations springdoc (`@Tag`, `@Operation` si besoin).

### Service : interface + implémentation

```java
public interface SiteService {

	SiteResponse getSite(String siteId);

	SiteResponse createSite(CreateSiteRequest request);

}
```

```java
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
class SiteServiceImpl implements SiteService {

	private final SiteRepository siteRepository;
	private final SiteMapper siteMapper;

	@Override
	public SiteResponse getSite(String siteId) {
		return siteRepository.findById(siteId)
			.map(siteMapper::toResponse)
			.orElseThrow(() -> new SiteNotFoundException(siteId));
	}

	@Override
	@Transactional
	public SiteResponse createSite(CreateSiteRequest request) {
		Site site = siteMapper.toEntity(request);
		return siteMapper.toResponse(siteRepository.save(site));
	}

}
```

- L'interface est `public` ; l'implémentation est **package-private** si possible (seule l'interface est visible des autres modules).
- `@Transactional(readOnly = true)` sur la classe, `@Transactional` sur les méthodes d'écriture.
- Le service prend et retourne des **DTO**, jamais des entités.

### Repository

```java
public interface SiteRepository extends JpaRepository<Site, String> {

	List<Site> findByStatus(String status);

}
```

- Méthodes dérivées de préférence ; `@Query` (JPQL) quand le nom devient illisible ; SQL natif seulement pour les fonctions TimescaleDB (`time_bucket`…).

### Entité

```java
@Entity
@Table(name = "sites")
@Getter
@Setter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Site {

	@Id
	@Column(name = "site_id")
	private String siteId;

	@Column(name = "site_name", nullable = false)
	private String siteName;

}
```

- **Le schéma est géré par `infra/db/init.sql`** (Hibernate est en `ddl-auto: validate`). Toute nouvelle table ou colonne s'ajoute d'abord dans `init.sql`, puis l'entité est alignée dessus : noms de table et de colonnes explicites (`@Table`, `@Column`), types compatibles.
- Clé composite (ex. hypertable `readings` : `site_id` + `ts`) : `@IdClass` ou `@EmbeddedId`.
- Pas de `@Data` ni de `@EqualsAndHashCode` / `@ToString` Lombok générés sur les entités (problèmes avec les proxys et le lazy loading).
- Relations en `FetchType.LAZY` par défaut.
- Dates : `Instant` pour `TIMESTAMPTZ`.

### DTO

```java
public record CreateSiteRequest(
		@NotBlank String siteName,
		@NotBlank String siteType,
		@Positive double capacityKw) {
}
```

- Toujours des `record`, immuables. Contraintes Bean Validation sur les DTO d'entrée.
- Suffixes : `*Request` en entrée, `*Response` en sortie.

### Mapper

- Classe `@Component` écrite à la main (`toResponse`, `toEntity`, `updateEntity`), pas de librairie de mapping tant que ce n'est pas nécessaire.

### Exceptions

- Exceptions métier non vérifiées (`extends RuntimeException`), nommées d'après le problème : `SiteNotFoundException`, `InvalidThresholdException`.
- Traduites en réponses HTTP par un `@RestControllerAdvice` global qui renvoie des `ProblemDetail` (RFC 9457). Ne pas faire de `try/catch` dans les controllers pour produire des erreurs HTTP.

## 5. Conventions Java générales

- **Java 21** : `record`, `switch` expressions, pattern matching `instanceof`, text blocks. `var` seulement si le type est évident à la lecture.
- **Injection par constructeur uniquement** : champs `private final` + `@RequiredArgsConstructor`. Jamais de `@Autowired` sur un champ.
- **Nommage** : identifiants en anglais (classes, méthodes, variables) ; Javadoc et commentaires en français, comme le reste du dépôt. Classes `PascalCase`, méthodes et champs `camelCase`, constantes `UPPER_SNAKE_CASE`, packages en minuscules sans `_`.
- **Null** : ne pas retourner `null` depuis un service ; `Optional` en retour de recherche (repository), jamais en paramètre ni en champ.
- **Logs** : `@Slf4j`, messages paramétrés (`log.info("Site {} créé", siteId)`), jamais de `System.out` ni de données sensibles (mots de passe, tokens).
- **Configuration** : propriétés typées via `@ConfigurationProperties` (record) plutôt que des `@Value` dispersés. Une seule config : `application/src/main/resources/application.yaml`.
- **Indentation** : tabulations, comme le code existant. Accolade ouvrante en fin de ligne, ligne vide après la déclaration de classe et avant l'accolade fermante.
- Pas de code mort, pas d'import inutilisé, pas de `catch` vide.

## 6. Tests

| Cible | Type de test | Outils |
|---|---|---|
| `ServiceImpl` | Unitaire | JUnit 5 + Mockito (`@ExtendWith(MockitoExtension.class)`), sans contexte Spring |
| Controller | Slice web | `@WebMvcTest(SiteController.class)` + `@MockitoBean` du service |
| Repository | Slice JPA | `@DataJpaTest` sur TimescaleDB via Testcontainers (jamais H2 : le schéma utilise des fonctions TimescaleDB) |
| Application complète | Intégration | `@SpringBootTest` + `@Import(TestcontainersConfiguration.class)` (module `application`) |

- Nommage : `<Classe>Test` pour l'unitaire, `<Classe>IT` ou `@SpringBootTest` pour l'intégration ; méthodes `shouldXxx_whenYyy`.
- Structure given / when / then, assertions AssertJ (`assertThat`).
- Spring Security est actif : les tests web doivent s'authentifier (`@WithMockUser`) ou tester explicitement le 401/403.

## 7. Dépendances Maven

- Versions gérées par `spring-boot-starter-parent` : ne jamais redéclarer un starter Spring Boot (ni Lombok, PostgreSQL, Testcontainers…) dans `<dependencyManagement>` ou avec une `<version>`.
- Une version qui n'est pas gérée par Boot se déclare comme propriété + entrée `<dependencyManagement>` dans le `pom.xml` parent (ex. `springdoc.version`).
- `spring-boot-maven-plugin` uniquement dans `application`.

## 8. Avant de terminer une tâche

1. `./mvnw clean verify` passe (Docker doit tourner pour les tests Testcontainers).
2. Le code est dans le bon module et le bon package, et respecte les couches (pas d'entité dans un controller, pas de repository d'un autre module).
3. Si le schéma change : `infra/db/init.sql` est mis à jour et la doc (`README.md`) aussi si besoin.
