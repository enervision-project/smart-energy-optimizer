---
name: java-conventions
description: Conventions de code Java et architecture en couches du core-api Enervision (Spring Boot 4, Java 21, monolithe modulaire Maven). À charger avant d'écrire, modifier ou relire du code Java dans services/core-api — nouvelle entité, endpoint REST, service, repository, DTO, mapper, exception ou test — et avant d'ajouter une dépendance Maven ou un module.
---

# Conventions Java — core-api

core-api est un **monolithe modulaire** : un seul jar exécutable (`application`) qui assemble des modules métier Maven (`user`, `diagnostic`, `telemetry`, `configuration`). Chaque module suit la même **architecture en couches** avec interfaces et implémentations. Voir `README.md` pour le build, la base et Docker.

## 1. Architecture en couches

```
Controller  →  Service (interface)  →  Repository (Spring Data)  →  Base
   ↑ DTO          ↑ implementation :          ↑ Entity
                    JpaSiteService…
```

| Couche | Rôle | Ne fait PAS |
|---|---|---|
| **Controller** (`api.controllers`) | HTTP : routes, validation des entrées (`@Valid`), codes de statut, DTO in/out | Pas de logique métier, pas d'accès au repository, n'expose jamais une entité |
| **Service** (`service`) | Logique métier, transactions, orchestration, conversion entité ↔ DTO via le mapper | Ne connaît pas HTTP (`ResponseEntity`, `HttpServletRequest`…) |
| **Repository** (`repository`) | Accès aux données (interfaces Spring Data JPA) | Pas de logique métier |
| **Entity** (`entity`) | Entités JPA, enums métier | Pas de dépendance vers les couches supérieures |

Règles de dépendance : une couche n'appelle que la couche juste en dessous. Le controller dépend de **l'interface** du service, jamais de l'implémentation.

## 2. Structure d'un module

Tout le code d'un module est sous `com.enervision.<module>` (sinon il n'est pas scanné par `com.enervision.Application`).

```
com.enervision.<module>
├── api/
│   ├── controllers/
│   │   └── <Nom>Controller.java
│   ├── dto/                    <Nom>Response, Create<Nom>Request, Update<Nom>Request
│   └── handlers/
│       └── <Module>ExceptionHandler.java
├── service/
│   ├── <Nom>Service.java       interface publique du module
│   └── implementation/
│       └── <Spécificité><Nom>Service.java   ex. JpaUserService, JwtAuthService
├── repository/
│   └── <Nom>Repository.java
├── entity/
│   ├── <Nom>.java              entité JPA
│   └── <Enum>.java             enums métier (ex. Role)
├── mapper/
│   └── <Nom>Mapper.java
├── exception/
│   └── <Nom>NotFoundException.java
└── security/                   (si besoin) beans de sécurité propres au module
```

Exemple de référence : le module `user` (auth et utilisateurs), qui suit exactement cette structure.

**Configuration Spring** :
- Les `@Configuration` propres à un module restent dans ce module (ex. `com.enervision.user.security.JwtConfig`).
- La configuration transverse, commune à tous les modules, va dans le module `application`, package `com.enervision.config` (ex. `SecurityConfig`).

## 3. Communication entre modules

- Un module n'utilise un autre module **que via son interface de service et ses DTO** (`com.enervision.<autre>.service.*Service`, `com.enervision.<autre>.api.dto.*`).
- Interdit : injecter le repository, utiliser l'entité ou une classe du package `service.implementation` d'un autre module.
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
class JpaSiteService implements SiteService {

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

- **Nommage** : l'interface porte le nom simple (`UserService`), car c'est le type utilisé partout (controllers, autres modules, tests). L'implémentation est nommée d'après ce qui la distingue : `JpaUserService`, `JwtAuthService`, `JwtTokenService`, `DatabaseUserDetailsService`. Pas de préfixe `I` (`IUserService`) ni de suffixe `Impl`. Les implémentations vont dans le sous-package `service.implementation`.
- L'interface est `public` ; l'implémentation est **package-private** si possible (seule l'interface est visible des autres modules).
- **Transactions** : `@Transactional(readOnly = true)` sur la classe, comme filet de sécurité (toute méthode publique tourne dans une transaction, et une écriture oubliée échoue au lieu de passer hors transaction). `@Transactional` sur chaque méthode d'écriture.
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
@NoArgsConstructor
public class Site {

	@Id
	@Column(name = "site_id")
	private String siteId;

	@Column(name = "site_name", nullable = false)
	private String siteName;

}
```

- **Le schéma est géré par `infra/db/init.sql`** (Hibernate est en `ddl-auto: validate`). L'entité doit être alignée sur ce schéma : noms de table et de colonnes explicites (`@Table`, `@Column`), types compatibles.
- **Ne pas modifier `infra/db/init.sql` (ni rien sous `infra/`) sans demande explicite.** Si une entité n'a pas encore sa table, le signaler (l'application ne démarrera pas en `validate`) et proposer le SQL, sans l'appliquer.
- Clé composite (ex. hypertable `readings` : `site_id` + `ts`) : `@IdClass` ou `@EmbeddedId`.
- Lombok sur les entités : `@Getter`, `@Setter` et `@NoArgsConstructor` (public, car le mapper crée l'entité depuis un autre package). Pas de `@Data`, `@AllArgsConstructor`, `@EqualsAndHashCode` ni `@ToString` générés : problèmes avec les proxys Hibernate et le lazy loading. Référence : `com.enervision.user.entity.User`.
- `@Entity` sans attribut `name` ; le nom de la table se met dans `@Table(name = "...")`.
- Timestamps techniques : `@CreationTimestamp` (`updatable = false`) et `@UpdateTimestamp`. Ils ne sont renseignés qu'au flush : utiliser `saveAndFlush` si la réponse doit les contenir.
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

- Exceptions métier non vérifiées (`extends RuntimeException`), nommées d'après le problème : `SiteNotFoundException`, `InvalidThresholdException`. Elles vont dans le package `exception` du module.
- Chaque module traduit ses propres exceptions en réponses HTTP `ProblemDetail` (RFC 9457) dans `api/handlers/<Module>ExceptionHandler`. Ce handler est un `@RestControllerAdvice(basePackages = "com.enervision.<module>")` package-private : `basePackages` le limite aux controllers du module pour qu'il n'interfère pas avec les autres.

```java
@RestControllerAdvice(basePackages = "com.enervision.user")
class UserExceptionHandler {

	@ExceptionHandler(UserNotFoundException.class)
	ProblemDetail handleUserNotFound(UserNotFoundException exception) {
		return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, exception.getMessage());
	}

}
```

- Les erreurs standard (validation `@Valid`, 404, 405…) sont déjà renvoyées en `ProblemDetail` grâce à `spring.mvc.problemdetails.enabled: true` ; inutile de les gérer dans les handlers.
- Ne pas faire de `try/catch` dans les controllers pour produire des erreurs HTTP.

### Sécurité

- **Tout endpoint est protégé par défaut** (jeton JWT obligatoire) par la chaîne globale `com.enervision.config.SecurityConfig` du module `application`. Ne pas créer d'autre `SecurityFilterChain` dans un module.
- Autorisations par rôle sur le controller, via des **méta-annotations** : `@AdminOnly` (`com.enervision.user.security`). Ne pas écrire `@PreAuthorize("hasRole('ADMIN')")` dans les controllers : la chaîne SpEL n'est pas vérifiée à la compilation. Les noms de rôle n'apparaissent en chaîne que dans la méta-annotation, qui doit correspondre à l'enum `Role` (`USER`, `ADMIN`). Pour une nouvelle règle, créer une nouvelle méta-annotation à côté d'`@AdminOnly`.

```java
@AdminOnly
@GetMapping
public List<UserResponse> getUsers() {
	return userService.getUsers();
}
```

- Utilisateur courant : `@AuthenticationPrincipal Jwt jwt`, puis `UUID.fromString(Objects.requireNonNull(jwt.getSubject()))`. L'id se passe ensuite au service ; le service ne lit pas le `SecurityContext`.
- Une nouvelle route publique s'ajoute dans `SecurityConfig` (et `@SecurityRequirements` vide sur le controller pour la doc OpenAPI).
- Émission / vérification des jetons et mots de passe : uniquement dans `com.enervision.user.security`. Ne jamais logger un mot de passe ni un jeton.

## 5. Conventions Java générales

- **Java 21** : `record`, `switch` expressions, pattern matching `instanceof`, text blocks. `var` seulement si le type est évident à la lecture.
- **Injection par constructeur uniquement** : champs `private final` + `@RequiredArgsConstructor`. Jamais de `@Autowired` sur un champ.
- **Langue du code : tout en anglais.** Identifiants (classes, méthodes, variables), Javadoc et commentaires, mais aussi messages d'exception et d'erreur HTTP, messages de log, annotations OpenAPI (`@Tag`, `@Operation`) et commentaires des fichiers de config (`application.yaml`, `pom.xml`, `Dockerfile`). Seule la documentation (README, skill) reste en français.
- **Nommage** : Classes `PascalCase`, méthodes et champs `camelCase`, constantes `UPPER_SNAKE_CASE`, packages en minuscules sans `_`.
- **Null** : ne pas retourner `null` depuis un service ; `Optional` en retour de recherche (repository), jamais en paramètre ni en champ. Null-safety avec les annotations JSpecify (`org.jspecify.annotations.NonNull` / `Nullable`), utilisées par Spring 7 : les reprendre quand on redéfinit une méthode d'une API Spring (ex. `loadUserByUsername(@NonNull String email)`).
- **Pas de chaîne magique répétée** : noms de claims, rôles, en-têtes… dans des constantes `static final` (ex. `JwtTokenService.ROLES_CLAIM`, `EMAIL_CLAIM`).
- **Chaînes** : concaténation avec `+` (`"User " + userId + " not found"`) ; pas de `String.format` ni de `.formatted()`.
- **Logs** : `@Slf4j`, toujours avec les placeholders SLF4J (`log.info("Site {} created", siteId)`), **jamais de concaténation** dans un log (la chaîne serait construite même si le niveau est désactivé). Jamais de `System.out` ni de données sensibles (mots de passe, tokens).
- **Configuration** : propriétés typées via `@ConfigurationProperties` (record, `@Validated`) plutôt que des `@Value` dispersés. Une seule config : `application/src/main/resources/application.yaml` (pas de profil Spring pour l'instant).
- **Secrets** (mots de passe, clés JWT, tokens) : **jamais dans un fichier versionné**, même en dev, et jamais de valeur par défaut dans `application.yaml`. Ils viennent du `.env` racine (gitignoré ; lu par Compose, et importé par Spring en lancement local) ou de variables d'environnement (secrets de la plateforme en déploiement). Un nouveau secret ou une nouvelle variable : placeholder dans `application.yaml`, entrée sans valeur réelle dans `.env.example`, et passage au conteneur dans `compose.yaml`. Préférer un défaut vide (`${MY_SECRET:}`) + `@NotBlank` sur la propriété, pour un message d'erreur clair au démarrage.
- **Indentation** : tabulations, comme le code existant. Accolade ouvrante en fin de ligne, ligne vide après la déclaration de classe et avant l'accolade fermante.
- Pas de code mort, pas d'import inutilisé, pas de `catch` vide.

## 6. Tests

| Cible | Type de test | Outils |
|---|---|---|
| Implémentation de service (`JpaUserService`…) | Unitaire | JUnit 5 + Mockito (`@ExtendWith(MockitoExtension.class)`), sans contexte Spring |
| Controller | Slice web | `@WebMvcTest(SiteController.class)` + `@MockitoBean` du service |
| Repository | Slice JPA | `@DataJpaTest` sur TimescaleDB via Testcontainers (jamais H2 : le schéma utilise des fonctions TimescaleDB) |
| Application complète | Intégration | `@SpringBootTest` dans le module `application`, base TimescaleDB via Testcontainers (dépendances déjà présentes ; aucun test de ce type pour l'instant) |
| Sécurité / JWT | Unitaire | Instancier la config directement (ex. `new JwtConfig()`), sans contexte Spring (voir `JwtTokenServiceTest`) |

- Les tests reprennent le package de la classe testée (ex. `service.implementation.JpaUserServiceTest`), ce qui donne accès aux classes package-private.
- Nommage : `<Classe>Test` pour l'unitaire, `<Classe>IT` ou `@SpringBootTest` pour l'intégration ; méthodes `shouldXxx_whenYyy`.
- Structure given / when / then, assertions AssertJ (`assertThat`).
- Spring Security est actif : les tests web doivent s'authentifier (`@WithMockUser`) ou tester explicitement le 401/403.

## 7. Dépendances Maven

- Versions gérées par `spring-boot-starter-parent` : ne jamais redéclarer un starter Spring Boot (ni Lombok, PostgreSQL, Testcontainers…) dans `<dependencyManagement>` ou avec une `<version>`.
- Une version qui n'est pas gérée par Boot se déclare comme propriété + entrée `<dependencyManagement>` dans le `pom.xml` parent (ex. `springdoc.version`).
- `spring-boot-maven-plugin` uniquement dans `application`.

## 8. Avant de terminer une tâche

1. `./mvnw clean verify` passe (Docker doit tourner si des tests Testcontainers existent).
2. Le code est dans le bon module et le bon package, et respecte les couches (pas d'entité dans un controller, pas de repository d'un autre module).
3. Si le schéma change : `infra/db/init.sql` est mis à jour et la doc (`README.md`) aussi si besoin.
