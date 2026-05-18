import 'facility.dart';

sealed class LookupResult {
  const LookupResult();
}

class LookupFound extends LookupResult {
  final Department department;
  const LookupFound(this.department);
}

class LookupAmbiguous extends LookupResult {
  final List<Department> candidates;
  const LookupAmbiguous(this.candidates);
}

class LookupNotFound extends LookupResult {
  const LookupNotFound();
}
